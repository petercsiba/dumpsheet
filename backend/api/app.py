# TODO(P1, dumpsheet migration): Separate out this file into smaller FastAPI modules
import datetime
import re
import uuid
from typing import Optional

import boto3
import jwt
import peewee  # noqa
from botocore.exceptions import NoCredentialsError
from fastapi import FastAPI, HTTPException, Cookie, Depends
from pydantic import BaseModel, EmailStr
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import Response
from supabase_auth import SyncGoTrueClient, AuthResponse

from common.aws_utils import get_bucket_url
from common.config import ENV, ENV_LOCAL, ENV_PROD, AWS_SECRET_ACCESS_KEY, AWS_ACCESS_KEY_ID, \
    POSTGRES_LOGIN_URL_FROM_ENV, GOTRUE_URL, GOTRUE_JWT_SECRET
# TODO(P2, dumpsheet migration): Instead of import the entire module, just import the classes.
from database import account, data_entry, models
from database.constants import (
    ACCOUNT_STATE_ACTIVE,
    ACCOUNT_STATE_MERGED,
    ACCOUNT_STATE_PENDING,
)
from database.models import BaseDataEntry, BaseEmailLog
from supawee.client import connect_to_postgres_i_will_call_disconnect_i_promise, disconnect_from_postgres_as_i_promised

s3 = boto3.client("s3", aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)


# ======= FAST API BOILERPLATE =======

app = FastAPI()
origins = []
local_origins = [
    "http://localhost:3000",  # Adjust this if needed
    "http://localhost:8080",  # Your server's port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]
prod_origins = [
    "https://dumpsheet.com",
    "https://www.dumpsheet.com",
    "https://app.dumpsheet.com",
    "https://api.dumpsheet.com",
]
if ENV == ENV_LOCAL:
    print(
        "INFO: Adding CORS Middleware for LOCAL Environment (DO NOT DO IN PRODUCTION)"
    )
    origins = local_origins
elif ENV == ENV_PROD:
    print(
        "INFO: Adding CORS Middleware for PROD Environment"
    )
    origins = prod_origins + local_origins  # TODO(P1, yolo): Remove local_origins
else:
    raise Exception(f"Unknown environment {ENV} cannot start server")

# Apply CORS middleware
# TODO(P1, devx): It would be nice to add a correlation id https://github.com/snok/asgi-correlation-id
#   Actually, we can likely just use the fly-request-id header maybe (at least present on the response)
#   curl -I -X GET https://api.dumpsheet.com/
app.add_middleware(
    CORSMiddleware,  # noqa
    allow_origins=origins,  # or use ["*"] to allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def startup():
    postgres_login_url = POSTGRES_LOGIN_URL_FROM_ENV
    # with client.connect_to_postgres(postgres_login_url):
    # Indeed, in AWS Lambda, it is generally recommended not to explicitly close database connections
    # at the end of each function invocation. Lambda execution context will freeze and thaw it.
    connect_to_postgres_i_will_call_disconnect_i_promise(postgres_login_url)  # lies


def shutdown():
    disconnect_from_postgres_as_i_promised()


app.add_event_handler("startup", startup)
app.add_event_handler("shutdown", shutdown)


# ======= API ENDPOINTS =======
@app.get("/")
def read_root():
    return {"status": "ok", "version": "1.0.0"}


def sign_in_anonymously() -> AuthResponse:
    # https://github.com/supabase/auth-py/blob/main/README.md
    headers = {
        "apiKey": GOTRUE_JWT_SECRET,
    }
    client = SyncGoTrueClient(
        url=GOTRUE_URL,
        headers=headers,
    )
    # TODO(P2, ux): Seems like Captcha should be passed in here
    # https://supabase.com/docs/guides/auth/auth-anonymous?queryGroups=language&language=python
    auth_response = client.sign_in_anonymously()
    # auth_response = {
    #     "user": {
    #         "id": "85014069-9137-40a5-ac56-835c124fe0a3",
    #         "aud": "authenticated",
    #         "role": "authenticated",
    #         "is_anonymous": True
    #     },
    #     "session": {
    #         "access_token": "eyJhbGciOiJIU...",
    #         "refresh_token": "PPXspKiu-T6AzZu1jvPMqg",
    #         "expires_in": 3600,
    #         "expires_at": 1725433359,
    #         "token_type": "bearer",
    #         "user": <same as above>
    #     }
    # }
    return auth_response


# UserFrontEnd is just a helper class to pass decoded JWT values
# https://phillyharper.medium.com/implementing-supabase-auth-in-fastapi-63d9d8272c7b
class UserFrontEnd(BaseModel):
    # user-id in the database
    user_id: str
    username: Optional[str] = None
    # Optional for anonymous, or phone based / social logins
    email: Optional[str] = None
    is_anonymous: bool


# TODO(P2, devx): Maybe better is to have a Depends(JWTBearer) for protected routes.
#   https://dev.to/j0/integrating-fastapi-with-supabase-auth-780
def maybe_get_current_user(access_token: str = Cookie(None)) -> Optional[UserFrontEnd]:
    try:
        # Decoding the JWT token
        decoded = jwt.decode(
            access_token,
            key=GOTRUE_JWT_SECRET,  # The secret key from Supabase CMS
            algorithms=["HS256"],  # Specifying the JWT algorithm
            audience="authenticated",  # Setting the audience
            options={"verify_aud": True}  # Enabling audience verification
        )
        # {
        #     'iss': 'http://127.0.0.1:54321/auth/v1',  # Local GOTRUE_URL
        #     'sub': '4fa826b0-e928-4441-9fea-0a713178507b',  # this the supabase user id
        #     'aud': 'authenticated',
        #     'exp': 1725476400,
        #     'iat': 1725472800,
        #     'role': 'authenticated',
        #     'aal': 'aal1',
        #     'amr': [{'method': 'anonymous', 'timestamp': 1725472800}],
        #     'session_id': '2d6849c8-c6cb-455f-840c-43dc4a307833',
        #     'is_anonymous': True
        # }

        # Extracting user data
        # TODO(P1, ux): What about users with phone number or anonymous ones?
        email = decoded.get("email")
        user_metadata = decoded.get("user_metadata", {})
        username = user_metadata.get("username")

        # Returning a user object
        return UserFrontEnd(
            user_id=decoded.get("sub"),
            username=username if username else email,
            email=email,
            is_anonymous=False,
        )
    # TODO(P1, ux): We should inform the user that their token has expired
    except jwt.ExpiredSignatureError as e:
        print(f"WARNING: Token expired {e}")
        return None
    except jwt.InvalidTokenError as e:
        print(f"ERROR: Invalid token {e}")
        return None


class GetPresignedUrlResponse(BaseModel):
    presigned_url: str  # actually required, but we oftentimes mess up and that messes up return code to 500
    email: Optional[EmailStr] = None
    account_id: Optional[str] = None  # uuid really


@app.get("/upload/voice", response_model=GetPresignedUrlResponse)
async def get_presigned_url(request: Request, response: Response, current_user: Optional[UserFrontEnd] = Depends(
    maybe_get_current_user
)):
    print(f"DEBUG DEBUG DEBUG: current_user {current_user}")
    if not current_user:
        auth_response = sign_in_anonymously()
        # So in subsequent requests the current_user will be logged in.
        response.set_cookie(
            key="access_token",
            value=f"Bearer {auth_response.session.access_token}",
            httponly=True,
        )

    # TODO(P0, user-migration): Move the Supabase Auth altogether; use new UserAccount object instead.
    #   Account will still be the central point of the schema; just that FrontEnd will only be exposed to User.
    x_account_id = request.headers.get("X-Account-Id")
    # Specify the S3 bucket and file name
    bucket_name = "requests-from-api-voxana"
    data_entry_id = uuid.uuid4()
    file_name = f"{data_entry_id}.webm"
    print(f"received upload request for data entry {data_entry_id}: account_id {x_account_id}")
    # We should get this from the request
    content_type = "audio/webm"

    try:
        # Generate a presigned S3 PUT URL
        presigned_url = s3.generate_presigned_url(
            "put_object",
            # Ideally, we would include `data_entry_id` as Metadata.
            Params={
                "Bucket": bucket_name,
                "Key": file_name,
                "ContentType": content_type,  # add this line
            },
            ExpiresIn=600,  # URL will be valid for 10 minutes
        )
        print("presigned_url generated")
    except NoCredentialsError:
        # Officially HTTPException should only be used with 4xx
        # TODO(P1, devx): This somewhat causes missing CORS headers on browser leading to a Red Herring.
        raise HTTPException(500, "error generating presigned URL: No AWS Credentials")

    # NOTE: To allow extra headers you need to allow-list them in the CORS policy
    # https://chat.openai.com/share/4e0034b2-4012-4ef9-97dc-e41b66bec335
    if x_account_id and x_account_id != "null" and x_account_id != "undefined":
        print(f"Received account_id: {x_account_id} type {type(x_account_id)}")
        acc = account.Account.get_by_id(x_account_id)
    else:
        # TODO(P0, dumpsheet migration): This IP onboarding is just too custom, moving to anonymous users.
        # Extract some identifiers - these should NOT be use for auth - but good enough for a demo.
        source_ip = request.client.host
        user_agent = "this is deprecated in the future"
        print(f"Received source_ip: {source_ip} and user_agent {user_agent}")
        acc = account.Account.get_or_onboard_for_ip(
            ip_address=source_ip, user_agent=user_agent
        )

    if bool(acc.user):
        # TODO(P0, auth): Support authed sessions somehow.
        raise HTTPException(403, "please sign in")
    # We only want to collect the email address if not already associated with this IP address.
    email = acc.get_email()
    account_id = str(acc.id)  # maybe we should have a UUIDEncoder

    # This BaseDataEntry is mapped to the uploaded file by the data_entry_id
    inserted = models.BaseDataEntry.insert(
        id=data_entry_id,
        account=acc,
        display_name=f"Voice recording upload from {(datetime.datetime.now().strftime('%B %d, %H:%M'))}",
        # TODO(P2, ux): Also persist the original file name (in case of uploads)
        idempotency_id=data_entry_id,
        # TODO(P1, devx): We should also store input_method (like recording, upload, ...).
        #   OR use different buckets as we already do for email, calls and recordings.
        input_type=content_type,
        input_uri=get_bucket_url(bucket=bucket_name, key=file_name),
        state=data_entry.STATE_UPLOAD_INTENT
        # output_transcript, processed_at are None
    ).execute()
    print(f"inserted data entries {inserted}")
    return GetPresignedUrlResponse(presigned_url=presigned_url, email=email, account_id=account_id)


class PostUpdateEmailRequest(BaseModel):
    email: str
    account_id: str  # uuid really


class PostUpdateEmailResponse(BaseModel):
    detail: str


# curl -X POST -d '{email: "petherz+curl@gmail.com", account_id: "f11a156d-2dd1-44a4-83de-3dca117765b8"}' https://api.dumpsheet.com/upload/voice  # noqa
# TODO(P0, dumpsheet migration): This IP onboarding is just too custom use Supabase Auth or other off-shelf solution.
@app.post("/upload/voice", response_model=PostUpdateEmailResponse, status_code=200)
def post_update_email(request: PostUpdateEmailRequest):
    # TODO(P0, ux): Actually process terms of service from tos_accepted
    account_id = request.account_id
    email_raw = request.email

    if not email_raw or not account_id:
        raise HTTPException(400, "both email and account_id parameters are required")
    email = str(email_raw).lower()
    print(f"handle_post_request_for_update_email {email}:{account_id}")

    print(f"looking for account with id {account_id}")
    acc: account.Account = account.Account.get_or_none(account.Account.id == account_id)
    if acc is None:
        raise HTTPException(404, "account not found")
    existing_email = acc.get_email()

    # so we can set it for its Onboarding object.
    onboarding = models.BaseOnboarding.get_or_none(models.BaseOnboarding.account == acc)
    if not bool(onboarding):
        raise HTTPException(404, "onboarding not found")

    # We want to be careful with this update as handling identities must be robust
    # 1. Check if such email already has an account (in theory there can be multiple onboardings for the same email)
    acc_for_email = account.Account.get_by_email_or_none(email)
    if bool(acc_for_email):
        print(f"Found existing account {acc_for_email.id} for email {email}")
        # However, if you want to indicate that the resource was already created prior to the request,
        # there isn't a specific HTTP status code for this situation.
        if str(acc_for_email.id) == str(account_id):
            return PostUpdateEmailResponse(detail="account already exists with the provided email")
        if bool(existing_email) and existing_email != email:
            raise HTTPException(
                409, "requested account is claimed by a different a email address"
            )
        new_account_id = acc_for_email.id
        try:
            # Different accounts, same email.
            # account.Account.merge_in(acc_for_email.id, account_id)
            onboarding.account_id = new_account_id
            onboarding.email = email
            onboarding.save()
            de_update_query = BaseDataEntry.update(account_id=new_account_id).where(
                BaseDataEntry.account_id == account_id
            )
            print(f"DataEntry update query: {de_update_query.sql}")
            num_de = de_update_query.execute()
            num_el = (
                BaseEmailLog.update(account_id=new_account_id)
                .where(BaseEmailLog.account_id == account_id)
                .execute()
            )
            acc.state = ACCOUNT_STATE_MERGED
            acc.merged_into_id = new_account_id
            acc.save()
            print(
                f"Updated 1 onboardings, {num_de} data entries and {num_el} email logs"
            )
            return PostUpdateEmailResponse(detail=f"account {account_id} merged into existing {new_account_id}")
        except Exception as e:
            raise HTTPException(
                500,
                f"could not merge accounts {account_id} -> {new_account_id} cause {e}",
            )

    # 2. Vice-versa, prevent overriding emails for existing acc by checking that account if already has claimed email
    if bool(existing_email):
        if existing_email != email:
            raise HTTPException(
                409, "requested account is claimed by a different a email address"
            )
        return PostUpdateEmailResponse(detail="account already exists with the provided email")

    # This means existing_account has NO associated User, AND the email is un-used,
    onboarding.email = email
    onboarding.save()
    if acc.state == ACCOUNT_STATE_PENDING:
        acc.state = ACCOUNT_STATE_ACTIVE
        acc.save()

    return PostUpdateEmailResponse(detail="account email updated")


class CallSetEmailRequest(BaseModel):
    phone_number: str
    message: str


class CallSetEmailResponse(BaseModel):
    detail: str


@app.post("/call/set-email", status_code=201, response_model=CallSetEmailResponse)
def call_set_email(request: CallSetEmailRequest):
    # TODO(P2, dumpsheet migration): This should be a separate endpoint for Twilio Functions
    # if api_key != TWILIO_FUNCTIONS_API_KEY:
    #    raise HTTPException(403, "x-api-key is required")

    phone_number = request.phone_number
    message = request.message
    print(f"received message from {phone_number}: {message}")
    if phone_number is None or message is None:
        raise HTTPException(400, "both phone_number and message are required params")

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    match = re.search(pattern, message)
    new_email_raw = match.group(0) if match else None
    if new_email_raw is None:
        raise HTTPException(400, "no email address found in message")
    new_email = new_email_raw.lower()

    acc = account.Account.get_by_phone_or_none(phone_number)
    if acc is None:
        raise HTTPException(500, f"account should be already present for {phone_number}")

    existing_email = acc.get_email()
    if existing_email is None:
        existing_onboarding = models.BaseOnboarding.get(
            models.BaseOnboarding.account_id == acc.id
        )
        existing_onboarding.email = new_email
        print(f"updating existing onboarding for {phone_number} to {new_email}")
        existing_onboarding.save()
        return CallSetEmailResponse(detail="email updated")
    elif existing_email == new_email:
        # TODO(P2, devx): This should be a 200, but what is the FastAPI way for 200 vs 201?
        return HTTPException(200, "email already set")
    assert existing_email != new_email
    raise HTTPException(
        400,
        f"cannot reset email through this endpoint, phone_number claimed by {existing_email}",
    )


def _parse_account_id_from_state_param(param: Optional[str]) -> Optional[uuid.UUID]:
    if not bool(param):
        print("State parameter is missing")
        return None

    account_id = None
    account_id_key_value = param.split(":")
    if len(account_id_key_value) == 2 and account_id_key_value[0] == "accountId":
        account_id_str = account_id_key_value[1]
        try:
            account_id = uuid.UUID(
                account_id_str, version=4
            )  # Assuming it's a version 4 UUID
            print(f"Valid Account ID: {account_id}")
        except ValueError:
            print(f"Invalid UUID format for {account_id_str}")
    else:
        print(f"Invalid state parameter {param}")

    return account_id
