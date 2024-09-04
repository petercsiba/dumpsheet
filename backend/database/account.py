import random
import string
import time
from typing import List, Optional

from peewee import DoesNotExist

from common.config import ALLOW_ONBOARDING_IP_MATCHING
from database.constants import ACCOUNT_STATE_PENDING
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


# TODO(P0, dumpsheet migration): The Account abstraction got too complicated, definitely REMOVE the IP based onboarding,
# and ideally just use the Supabase functionality for simplicity and it is something I want to learn anyway.
class Account(BaseAccount):
    class Meta:
        table_name = "account"

    def get_email(self) -> Optional[str]:
        if bool(self.user):
            return User.get_by_id(self.user).email

        if bool(self.merged_into_id):
            if self.merged_into_id != self.id:
                return Account.get_by_id(self.merged_into_id).get_email()
            else:
                print(f"ERROR: for account {self.id} merged_into_id equals itself")

        try:
            onboarding_email = (
                BaseOnboarding.select()
                .where(
                    (BaseOnboarding.account == self.id)
                    & (BaseOnboarding.email.is_null(False))
                    & (BaseOnboarding.email != "")
                )
                .order_by(BaseOnboarding.created_at.desc())
                .get()
                .email
            )
            if onboarding_email:
                return onboarding_email
        except DoesNotExist:
            print(f"WARNING: Account.get_mail: no email found for account {self.id}")
        return None

    def get_shareable_spreadsheet_link(self) -> Optional[str]:
        if self.gsheet_id is None:
            # Refresh to double-check
            acc = Account.get_by_id(self.id)
            if acc.gsheet_id is None:
                print(
                    f"ERROR: tried to share gsheets link for account not having a gsheet_id: {acc.id}"
                )
                return None
        else:
            acc = self

        # Construct the shareable link
        return f"https://docs.google.com/spreadsheets/d/{acc.gsheet_id}/edit"

    def get_phone(self) -> Optional[str]:
        if bool(self.user):
            return User.get_by_id(self.user).phone

        try:
            onboarding_phone = (
                BaseOnboarding.select()
                .where(
                    (BaseOnboarding.account == self.id)
                    & (BaseOnboarding.phone.is_null(False))
                    & (BaseOnboarding.phone != "")
                )
                .order_by(BaseOnboarding.created_at.desc())
                .get()
                .phone
            )
            if onboarding_phone:
                return onboarding_phone
        except DoesNotExist:
            print(f"WARNING: Account.get_phone: no phone found for account {self.id}")

        return None

    # @staticmethod
    # # TODO(P2): This feels like a too dangerous function to have around
    # def merge_in(new_account_id, old_account_id):
    #     new_account = BaseAccount.get_or_none(BaseAccount.id == new_account_id)
    #     if new_account is None:
    #         raise ValueError(f"new_account_id {new_account_id} must exist")
    #
    #     old_account = BaseAccount.get_or_none(BaseAccount.id == old_account_id)
    #     if old_account is None:
    #         raise ValueError(f"old_account_id {old_account_id} must exist")
    #
    #     with database_proxy.transaction() as tx:
    #         print(f"merging {old_account_id} into {new_account_id}")
    #         num_onb = BaseOnboarding.update(account_id=new_account_id).where(
    #           BaseOnboarding.account_id == old_account_id).execute()
    #         num_de = BaseDataEntry.update(account_id=new_account_id).where(
    #           BaseDataEntry.account_id == old_account_id).execute()
    #         num_el = BaseEmailLog.update(account_id=new_account_id).where(
    #           BaseEmailLog.account_id == old_account_id).execute()
    #         tx.commit()
    #
    #     assert BaseOnboarding.get_or_none(BaseOnboarding.account_id == old_account_id) is None
    #     # old_account.delete_instance()
    #     print(f"Account.merge_in updated {num_onb} onboardings, {num_de} data entries and {num_el} email logs")

    @staticmethod
    def get_by_email_or_none(email_raw: str) -> Optional["Account"]:
        email = email_raw.lower()
        # For accounts which have already explicitly signed up
        user = User.get_or_none(User.email == email)
        if bool(user):
            return Account.get(Account.user == user)

        # For accounts only going through onboarding
        onboarding = (
            BaseOnboarding.select()
            .where(BaseOnboarding.email == email)
            .order_by(BaseOnboarding.created_at.desc())
            .limit(1)
            .first()
        )
        if bool(onboarding):
            return Account.get_by_id(onboarding.account_id)

        return None

    @staticmethod
    def get_or_onboard_for_email(
        email: str,
        utm_source: str,
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
            print(f"Account already exists for email {email}")
            return account

        print(f"Account onboarding for email {email}")
        account_id = (
            BaseAccount.insert(
                user=None,  # only during sign up
                full_name=full_name,
            )
            .on_conflict_ignore()
            .execute()
        )
        BaseOnboarding.insert(
            email=email,
            account_id=account_id,
            utm_source=utm_source,
            **onboarding_kwargs,
        ).execute()
        account = Account.get_by_id(account_id)
        print(f"onboarded account {account}")
        return account

    @staticmethod
    def get_or_onboard_for_ip(ip_address: str, user_agent: str) -> "Account":
        # TODO(hack): We always generate a new "anonymous identifier" for our local network.
        if ip_address in ["76.133.98.247", "172.16.9.186"]:
            anonymous_identifier = f"{ip_address}-{str(time.time())}"
            print(
                f"HACK: anonymous_identifier rewritten for our local ip to {anonymous_identifier}"
            )
        else:
            anonymous_identifier = f"{ip_address}-{user_agent}"

        if str(ALLOW_ONBOARDING_IP_MATCHING) == "1":
            onboarding: Optional[BaseOnboarding] = BaseOnboarding.get_or_none(
                BaseOnboarding.ip_address == anonymous_identifier
            )
            if bool(onboarding):
                print(
                    f"found account {onboarding.account_id} for anonymous_identifier {anonymous_identifier}"
                )
                return Account.get_by_id(onboarding.account_id)
        else:
            anonymous_identifier = f"{ip_address}-{str(time.time())}"
            print(
                f"ALLOW_ONBOARDING_IP_MATCHING is {ALLOW_ONBOARDING_IP_MATCHING} - will do new onboarding"
            )

        print(f"onboarding new account for anonymous_identifier {anonymous_identifier}")
        account_id = BaseAccount.insert(state=ACCOUNT_STATE_PENDING).execute()
        BaseOnboarding.insert(
            ip_address=anonymous_identifier,
            account_id=account_id,
            utm_source="ip_address",
        ).execute()
        account = Account.get_by_id(account_id)
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
            return Account.get_by_id(onboarding.account_id)

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
        account_id = (
            BaseAccount.insert(
                user=None,  # only during sign up
                full_name=full_name,
            )
            .on_conflict_ignore()
            .execute()
        )
        BaseOnboarding.insert(
            phone=phone, account_id=account_id, utm_source="phone", **onboarding_kwargs
        ).execute()
        account = Account.get_by_id(account_id)
        print(f"onboarded account {account}")
        return account

