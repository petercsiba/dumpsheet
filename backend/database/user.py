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


# TODO(P1, devx): At some point we have to setup auth locally:
# https://supabase.com/docs/guides/cli/local-development#use-auth-locally
class User(BaseUsers):
    class Meta:
        table_name = "users"

    @staticmethod
    def exists_by_email(email_raw: str) -> bool:
        email = email_raw.lower()
        return User.select().where(User.email == email).exists()

    @staticmethod
    def get_by_email(email: str):
        return User.get(User.email == email)

    def contact_method(self) -> str:
        if self.email is not None or self.phone is None:
            return "email"
        return "sms"  # TODO(P2, ux): we likely want to distinguish between sms and call
