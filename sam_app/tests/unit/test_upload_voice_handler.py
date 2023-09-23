import json
import uuid
from typing import Dict, Optional
from uuid import UUID

import pytest

from database.account import Account
from database.client import (
    POSTGRES_LOGIN_URL_FROM_ENV,
    connect_to_postgres_i_will_call_disconnect_i_promise,
    disconnect_from_postgres_as_i_promised,
)
from database.data_entry import STATE_UPLOAD_INTENT
from database.models import BaseDataEntry, BaseOnboarding

from ...upload_voice import app
from ...upload_voice.app import TWILIO_FUNCTIONS_API_KEY


@pytest.fixture(scope="module", autouse=True)
def db_connection():
    db = connect_to_postgres_i_will_call_disconnect_i_promise(
        POSTGRES_LOGIN_URL_FROM_ENV
    )
    print("truncating tables")
    db.execute_sql('TRUNCATE TABLE "data_entry" CASCADE')
    db.execute_sql('TRUNCATE TABLE "onboarding" CASCADE')
    db.execute_sql('TRUNCATE TABLE "account" CASCADE')

    yield

    disconnect_from_postgres_as_i_promised()


def get_event_fixture(
    method: str, path: str, body: Dict, extra_headers: Optional[Dict] = None
):
    if extra_headers is None:
        extra_headers = {}
    headers = {"origin": "https://app.voxana.ai"}
    headers.update(**extra_headers)

    return {
        "httpMethod": method,
        "path": path,
        "body": json.dumps(body),
        "headers": headers,
        "resource": path,
        "requestContext": {
            "httpMethod": method,
            "resourcePath": path,
            "path": "Prod/",
            "requestId": str(uuid.uuid4()),
            "identity": {
                "sourceIp": "127.0.0.1",
            },
        },
        "isBase64Encoded": False,
    }


def create_data_entry_fixture(
    account_id: uuid.UUID, input_type: str = "input_type"
) -> UUID:
    return BaseDataEntry.insert(
        account_id=account_id,
        display_name=f"Data entry for {account_id}",
        idempotency_id=account_id,
        input_type=input_type,
        state=STATE_UPLOAD_INTENT,
    ).execute()


def get_event_for_post_call_set_email(account_id: UUID):
    return {
        "body": json.dumps(
            {"email": "petherz+call.set.email@gmail.com", "account_id": str(account_id)}
        ),
        "resource": "/call/set-email",
        "requestContext": {
            "httpMethod": "POST",
            "requestId": "c6af9ac6-7b61-11e6-9a41-1234deadbeef",
            "identity": {
                "sourceIp": "127.0.0.1",
            },
        },
        "headers": {
            "origin": "https://app.voxana.ai",
        },
        "httpMethod": "POST",
        "path": "/call/set-email",
    }


def test_lambda_handler_get_upload_voice(db_connection):
    req = get_event_fixture("GET", "/upload/voice", {})
    ret = app.lambda_handler(req, "")
    assert ret["statusCode"] == 201

    data = json.loads(ret["body"])

    assert "presigned_url" in data
    assert "email" in data
    assert "account_id" in data


def test_lambda_handler_post_upload_voice(db_connection):
    orig_account = Account.get_or_onboard_for_ip("127.0.0.1")

    req = get_event_fixture(
        "POST",
        "/upload/voice",
        {"email": "petherz+test1@gmail.com", "account_id": str(orig_account.id)},
    )
    ret = app.lambda_handler(req, "")
    assert ret["statusCode"] == 200

    updated_onboarding = BaseOnboarding.get(BaseOnboarding.account == orig_account)
    expected_email = "petherz+test1@gmail.com"
    assert updated_onboarding.email == expected_email
    # Test some extra functionality on the Account class for more confidence in my sleep
    updated_account = Account.get_by_id(orig_account.id)
    assert updated_account.get_email() == expected_email
    assert Account.get_by_email_or_none(expected_email).id == orig_account.id
    assert Account.get_or_onboard_for_email(expected_email).id == orig_account.id

    # Cannot reset email to other just like that
    req = get_event_fixture(
        "POST",
        "/upload/voice",
        {"email": "tryingtopwn@gmail.com", "account_id": str(orig_account.id)},
    )
    ret = app.lambda_handler(req, "")
    assert ret["statusCode"] == 409
    body = json.loads(ret["body"])
    assert (
        body["error"] == "requested account is claimed by a different a email address"
    )


def test_lambda_handler_post_upload_voice_new_account_same_email(db_connection):
    orig_account = Account.get_or_onboard_for_ip("127.0.0.1")
    orig_onboarding = BaseOnboarding.get(BaseOnboarding.account == orig_account)
    orig_onboarding.email = "existing@gmail.com"
    orig_onboarding.save()
    new_account = Account.get_or_onboard_for_ip("127.0.0.2")
    new_onboarding = BaseOnboarding.get(BaseOnboarding.account == new_account)
    new_data_entry_id = create_data_entry_fixture(new_account.id)

    # Double-check setup
    assert orig_account.id != new_account.id
    assert orig_onboarding.account_id != new_onboarding.account_id
    assert orig_account.get_email() == "existing@gmail.com"
    print(
        f"orig:({orig_onboarding.id}, {orig_account.id}) new:({new_onboarding.id}, {new_account.id})"
    )

    # Other un-claimed onboarding / account pair wants to have the same email
    req = get_event_fixture(
        "POST",
        "/upload/voice",
        {"email": "existing@gmail.com", "account_id": str(new_account.id)},
    )
    ret = app.lambda_handler(req, "")
    assert ret["statusCode"] == 200

    # The new onboarding got updated
    updated_onboarding = BaseOnboarding.get_by_id(new_onboarding.id)
    assert updated_onboarding.email == "existing@gmail.com"
    assert updated_onboarding.account_id == orig_account.id

    # No onboarding points to it
    assert BaseOnboarding.get_or_none(BaseOnboarding.account == new_account) is None

    # Data entry was updated
    updated_data_entry = BaseDataEntry.get_by_id(new_data_entry_id)
    assert updated_data_entry.account_id == orig_account.id


def test_lambda_handler_call_set_email(db_connection):
    phone_number = "+16502106516"
    orig_account = Account.get_or_onboard_for_phone(
        phone=phone_number,
        full_name="Peter Csiba",
        onboarding_kwargs={"phone_carrier_info": "kinda optional"},
    )

    req = get_event_fixture(
        "POST",
        "/call/set-email",
        body={
            "phone_number": phone_number,
            "message": "Here you go Voxana, my email is petherz+phone@gmail.com. Looking forward to your draft!",
        },
        extra_headers={"x-api-key": TWILIO_FUNCTIONS_API_KEY},
    )
    ret = app.lambda_handler(req, "")
    assert ret["statusCode"] == 201
    assert orig_account.get_phone() == phone_number

    data = json.loads(ret["body"])
    assert data["info"] == "email updated"
