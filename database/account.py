import random
import string
from typing import Optional

from database.models import BaseAccount, BaseOnboarding
from database.user import User


def generate_temp_password(length=8):
    # Define the characters we'll use to generate the password
    all_characters = string.ascii_letters + string.digits + string.punctuation
    if length < 8:
        print("Password length should be at least 8 characters")
        return
    # Generate a random password of specified length
    password = "".join(random.choice(all_characters) for _ in range(length))
    return password


class Account(BaseAccount):
    class Meta:
        db_table = "account"

    def get_email(self) -> Optional[str]:
        if bool(self.user):
            return User.get_by_id(self.user).email
        if bool(self.onboarding):
            return BaseOnboarding.get_by_id(self.onboarding).email
        print(f"Account.get_mail: no onboarding nor user for account {self.id}")
        return None

    def get_phone(self) -> Optional[str]:
        if bool(self.user):
            return User.get_by_id(self.user).phone
        if bool(self.onboarding):
            return BaseOnboarding.get_by_id(self.onboarding).phone
        print(f"Account.get_phone: no onboarding nor user for account {self.id}")
        return None

    @staticmethod
    def get_by_email_or_none(email: str) -> Optional["Account"]:
        # For accounts which have already explicitly signed up
        user = User.get_or_none(User.email == email)
        if bool(user):
            return Account.get(Account.user == user)

        # For accounts only going through onboarding
        onboarding = BaseOnboarding.get_or_none(BaseOnboarding.email == email)
        if bool(onboarding):
            return Account.get(Account.onboarding == onboarding)

        return None

    @staticmethod
    def get_or_onboard_for_email(
        email: str,
        # TODO(P1, features): Actually support sign up by phone
        # phone: Optional[str] = None,
        # temp_password: Optional[str] = None,
        full_name: Optional[str] = None,
        onboarding_kwargs=None,
    ) -> "Account":
        if onboarding_kwargs is None:
            onboarding_kwargs = {}

        account = Account.get_by_email_or_none(email)
        if bool(account):
            return account

        print(f"onboarding account for email {email}")
        onboarding = BaseOnboarding.insert(email=email, **onboarding_kwargs).execute()
        account_id = (
            BaseAccount.insert(
                onboarding=onboarding,
                user=None,  # only during sign up
                full_name=full_name,
            )
            .on_conflict_ignore()
            .execute()
        )
        account = Account.get_by_id(account_id)
        print(f"onboarded account {account}")
        return account

    # TODO(P1, ux/analytics): On second thought, would be better to have Onboarding.account_id,
    #   we always create the Account, while people can change IPs, or go from App to calls and would be nice
    #   to link everything to the same account.
    @staticmethod
    def get_or_onboard_for_ip(
        ip_address: str,
    ) -> "Account":
        onboarding = BaseOnboarding.get_or_none(BaseOnboarding.ip_address == ip_address)
        if bool(onboarding):
            return Account.get(Account.onboarding == onboarding)

        print(f"onboarding account for ip_address {ip_address}")
        onboarding = BaseOnboarding.insert(ip_address=ip_address).execute()
        account_id = (
            BaseAccount.insert(onboarding=onboarding).on_conflict_ignore().execute()
        )
        account = Account.get_by_id(account_id)
        print(f"onboarded account {account}")
        return account

    @staticmethod
    def get_by_phone_or_none(phone: str) -> Optional["Account"]:
        # For accounts which have already explicitly signed up
        user = User.get_or_none(User.phone == phone)
        if bool(user):
            return Account.get(Account.user == user)

        # For accounts only going through onboarding
        # TODO(ux, P1): It is important to use the same canonical phone-number number format (phonenumbers library?)
        onboarding = BaseOnboarding.get_or_none(BaseOnboarding.phone == phone)
        if bool(onboarding):
            return Account.get(Account.onboarding == onboarding)

        return None

    @staticmethod
    def get_or_onboard_for_phone(
        phone: str,
        full_name: Optional[str] = None,
        onboarding_kwargs=None,
    ) -> "Account":
        if onboarding_kwargs is None:
            onboarding_kwargs = {}

        account = Account.get_by_phone_or_none(phone)
        if bool(account):
            return account

        print(f"onboarding account for phone {phone}")
        onboarding = BaseOnboarding.insert(phone=phone, **onboarding_kwargs).execute()
        account_id = (
            BaseAccount.insert(
                onboarding=onboarding,
                user=None,  # only during sign up
                full_name=full_name,
            )
            .on_conflict_ignore()
            .execute()
        )
        account = Account.get_by_id(account_id)
        print(f"onboarded account {account}")
        return account
