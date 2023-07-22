import uuid

from common.config import SENDER_EMAIL, SUPPORT_EMAIL
from database.account import Account
from database.models import BaseEmailLog


# The overarching logic is:
# * Pass around EmailLog params potentially filling them in
# * After sending, we persist it in our DB for idempotency_id check
# TODO(P3, correctness): We should persist both intent, and actually sent. SES is quite stable, so let it be for now.
class EmailLog(BaseEmailLog):
    class Meta:
        db_table = "email_log"

    def get_recipient_first_name(self):
        return self.recipient_full_name.split()[0]

    def fill_in_account(self):
        if self.account is None:
            print(f"log_email: updating user_id for {self.recipient}")
            self.account = Account.get_by_email_or_none(self.recipient)

    def log_email(self):
        if bool(self.id):
            raise ValueError(
                f"yo, you are likely trying to re-use params for already sent email {self.idempotency_id}, use deepcopy"
            )

        self.fill_in_account()

        print(f"log_email: to {self.recipient} idempotency_id: {self.idempotency_id}")
        self.save()

    def check_if_already_sent(self) -> bool:
        return (
            EmailLog.select()
            .where(
                EmailLog.recipient == self.recipient,
                EmailLog.idempotency_id == self.idempotency_id,
            )
            .exists()
        )

    @staticmethod
    def get_email_reply_params_for_account_id(
        account_id: uuid, idempotency_id: str, subject: str
    ):
        account = Account.get_by_id(account_id)
        return EmailLog(
            sender=SENDER_EMAIL,
            recipient=account.get_email(),
            recipient_full_name=account.full_name,
            subject=subject,
            reply_to=SUPPORT_EMAIL,  # We skip the orig_to_address, as that would trigger another transcription.
            idempotency_id=idempotency_id,
        )
