import os

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from typing import Optional

from common.utils import Timer


FROM_PHONE_NUMBER = "+18554137047"


class TwilioClient:
    def __init__(self, from_phone=FROM_PHONE_NUMBER):
        print(f"TwilioClient init from_phone {from_phone}")
        self.account_sid = os.environ['TWILIO_ACCOUNT_SID']
        self.auth_token = os.environ['TWILIO_AUTH_TOKEN']
        self.from_phone = from_phone
        self.client = Client(self.account_sid, self.auth_token)
        self.call_count = 0

    # TODO(P1, ux): Support idempotency keys here too.
    # TODO(P0, ux): Figure out that consent https://www.twilio.com/en-us/legal/messaging-policy
    def send_sms(self, to_phone, body) -> Optional[str]:
        try:
            with Timer("Twilio Send SMS"):
                print(f"Sending SMS to {to_phone} with body {body}")
                message = self.client.messages.create(
                    from_=self.from_phone,
                    body=body,
                    to=to_phone
                )
                self.call_count += 1
                return message.sid
        except TwilioRestException as e:
            print(f"Failed to send SMS: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
