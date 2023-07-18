import re
from typing import Optional, Tuple
from urllib.parse import unquote

import phonenumbers


# I have sweat a lot on this function so keeping it around - using S3 Metadata is definitely more robust (and PII).
# TODO(P2, devx): Maybe get rid of this
def extract_phone_number_from_filename(
    file_name: str,
) -> Tuple[Optional[str], Optional[str]]:
    # Example bucket_keys:
    # +16502100123-Undefined Peter Csiba-CA7e063a0e33540dc2496d09f5b81e42aa.wav
    # undefined--CA0f5399aafc07cf9991eb0be0d1ab7c52.wav
    # So parse those data now
    pattern = r"(?P<phone>\+?\d+|undefined)?-?(?P<name>[^-\n]*|undefined)?-?(?P<callSID>[^-\n]*)"
    # unquote-ing here to get rid of any % (if no % then no change)
    match = re.search(pattern, unquote(file_name))
    phone_number = None
    full_name = None
    if match:
        result = match.groupdict()
        full_name = result["name"].replace("Undefined", "").strip()
        phone_number = result["phone"]

        # Check if phone number is valid
        if phone_number != "undefined":
            try:
                parsed_number = phonenumbers.parse(phone_number, "US")
                formatted_number = phonenumbers.format_number(
                    parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                )
                print(formatted_number)
            except phonenumbers.phonenumberutil.NumberParseException:
                print(f"ERROR: Invalid phone number {phone_number} for {file_name}")
                # TODO(P1, correctness): If wrong format still let is pass for now to increase chances of results
                # phone_number = None
        else:
            phone_number = None
    if phone_number is None:
        print(
            f"ERROR: Cannot match the phone_number-name-callSID format for {file_name}"
        )

    return phone_number, full_name
