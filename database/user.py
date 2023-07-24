import random
import string

from database.models import BaseUsers


def generate_temp_password(length=8):
    # Define the characters we'll use to generate the password
    all_characters = string.ascii_letters + string.digits + string.punctuation
    if length < 8:
        print("Password length should be at least 8 characters")
        return
    # Generate a random password of specified length
    password = "".join(random.choice(all_characters) for _ in range(length))
    return password


class User(BaseUsers):
    class Meta:
        db_table = "users"

    @staticmethod
    def exists_by_email(email: str) -> bool:
        return User.select().where(User.email == email).exists()

    @staticmethod
    def get_by_email(email: str):
        return User.get(User.email == email)

    def contact_method(self) -> str:
        if self.email is not None or self.phone is None:
            return "email"
        return "sms"  # TODO(P2, ux): we likely want to distinguish between sms and call


# TODO(P0, devx): Move this out of database package
"""
    @staticmethod
    def get_or_create_using_rest(
        email: Optional[str],
        phone: Optional[str] = None,
        temp_password: Optional[str] = None,
        full_name: Optional[str] = None,
    ):
        if email is None and phone is None:
            raise ValueError(
                "get_or_create_using_rest requires either email or phone to be specified"
            )

        if temp_password is None:
            temp_password = generate_temp_password(10)

        supabase_client = get_supabase_client()
        # TODO(P1, features): Actually support sign up by phone
        if bool(email) and not User.exists_by_email(email):
            # User does not exist, so sign them up.
            print(f"sign_up user start {email}")
            # TODO(P0, onboarding): Users will need to change their initial password (or the lack of existence of it).
            #  We would need to implement that screen initial screen (part of larger onboarding).
            sign_up_res = supabase_client.auth.sign_up(
                {
                    "email": email,
                    "password": temp_password,
                }
            )
            print(f"sign_up user_id done {sign_up_res.user.id}")
            supabase_client.auth.sign_out()

        # For backend purposes, we really only care about the User object rather than the supabase session.
        res = User.get_by_email(email)
        BaseAccount.insert(
            user_id=res.id, full_name=full_name
        ).on_conflict_ignore().execute()
        return res

    # TODO(P0, onboarding): Users will need to set password / connect their SSO - find some Next.js code for it.
    @staticmethod
    def get_magic_link_and_create_user_if_does_not_exists(email: str) -> Session:
        # If the user doesn't exist, sign_in_with_otp() will signup the user instead.
        supabase_client = get_supabase_client()
        response = supabase_client.auth.sign_in_with_otp(
            {
                "email": email,
                "options": {
                    "email_redirect_to": "https://app.voxana.ai/"
                    if is_running_in_aws()
                    else "http://localhost:3000/"
                },
            }
        )
        print(f"sign_in_with_otp for {email} yielded {response}")
        return response"""
