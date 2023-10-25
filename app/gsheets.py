import re
import time
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

import gspread
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from gspread import Spreadsheet, Worksheet

from app.email_template import button_template, simple_email_body_html
from app.emails import send_email
from app.form import FieldDefinition, FormData, FormDefinition, FormName
from app.form_library import FOOD_LOG_FIELDS
from common.config import GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY
from database.account import Account
from database.client import POSTGRES_LOGIN_URL_FROM_ENV, connect_to_postgres
from database.email_log import EmailLog

# TODO(P1, devx): Move FieldDefinition, FormDefinition into this library; they act as:
# * form headers
# * chat-gpt query builders


_google_credentials_json = {
    "type": "service_account",
    "project_id": "voxana",
    "private_key_id": "d86eb11b9a5c4089f3426f7e5561caa93af91daa",
    "private_key": GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY,
    "client_email": "sheets@voxana.iam.gserviceaccount.com",
    "client_id": "110647437514248117236",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/sheets%40voxana.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com",
}


# Bit hacky as it is responsible for both authorization with Google API, AND managing the spreadsheet itself.
# Stateful.
# Some errors to share to set expectations:
# * gspread.exceptions.APIError: {'code': 400, 'message': 'Range (Sheet1!A1003) exceeds grid limits.
#                                 Max rows: 1002, max columns: 26', 'status': 'INVALID_ARGUMENT'}
class GoogleClient:
    def __init__(self):
        self.gspread_client = None
        self.drive_service = None
        self.spreadsheet: Optional[Spreadsheet] = None

    def login(self):
        # Initialize API
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            credentials = Credentials.from_service_account_info(
                _google_credentials_json, scopes=scopes
            )
            print("Login to google services")
            self.gspread_client = gspread.authorize(credentials)
            self.drive_service = build("drive", "v3", credentials=credentials)
        except Exception as ex:
            print(f"ERROR: Cannot initialize Google Spreadsheets {ex}")

    def create(self, spreadsheet_name) -> Optional[Spreadsheet]:
        if self.gspread_client is None:
            print("ERROR: Cannot create spreadsheet cause we didn't login")
            return None

        self.spreadsheet: Spreadsheet = self.gspread_client.create(spreadsheet_name)
        print(
            f"gsheets  Created spreadsheet {spreadsheet_name} of {type(self.spreadsheet)}"
        )

        return self.spreadsheet

    def open_by_key(self, spreadsheet_key) -> Optional[Spreadsheet]:
        if self.gspread_client is None:
            print("ERROR: Cannot open spreadsheet cause we didn't login")
            return None

        self.spreadsheet: Spreadsheet = self.gspread_client.open_by_key(spreadsheet_key)
        print(
            f"gsheets  Opened spreadsheet {spreadsheet_key} of {type(self.spreadsheet)}"
        )

        return self.spreadsheet

    @staticmethod
    # Attempts to extract invalidSharingRequest
    def _get_error_reason(gsheets_err: HttpError):
        # error_details should be like:
        # [{'message': 'Bad Request. User message: "You are trying ... vite this recipient."',
        # 'domain': 'global', 'reason': 'invalidSharingRequest'}]
        if (
            isinstance(gsheets_err.error_details, dict)
            and "reason" in gsheets_err.error_details
        ):
            return gsheets_err.error_details["reason"]

        match = re.search(r"'reason': '([^']+)'", str(gsheets_err))
        if match:
            return match.group(1)

        # reason is of form: Bad Request. User message: "You are trying ...  to invite this recipient
        return gsheets_err.reason

    def share_with(self, acc: Account):
        email = acc.get_email()
        if email is None:
            # Even if no email - we still continue filling in the sheet as it can be shared later on.
            print(
                f"WARNING: Cannot share gsheet for account {acc.id} cause no email was found"
            )
            return

        # Share spreadsheet
        file_id = self.spreadsheet.id

        print(f"gsheets  Sharing spreadsheet {self.spreadsheet.id} with {email}")
        user_permission = {
            "type": "user",
            "role": "writer",
            # 'role': 'owner',  # TODO: would be nice to have the user as owner
            # Consent is required to transfer ownership of a file to another user.
            "emailAddress": email,
            # 'allowFileDiscovery': True  # allowFileDiscovery is not valid for individual users
        }
        try:
            # First, we try to share with sendNotificationEmail=False and sending a customized email.
            self.drive_service.permissions().create(
                fileId=file_id,
                body=user_permission,
                fields="id",
                # transferOwnership=True,  # For role=owner
                sendNotificationEmail=False,
            ).execute()

            # Construct the shareable link
            shareable_link = f"https://docs.google.com/spreadsheets/d/{file_id}/edit"
            send_gsheets_shareable_link(
                account_id=acc.id, shareable_link=shareable_link
            )

        except HttpError as gsheets_err:
            print(
                f"WARNING: gsheets cannot share spreadsheet {self.spreadsheet.id} "
                f"with {email} cause {gsheets_err.reason}"
            )
            # For non-existing Google accounts sendNotificationEmail must be true, otherwise an error is received:
            # You are trying to invite peter+localtest@voxana.ai.
            # Since there is no Google account associated with this email address,
            # you must check the "Notify people" box to invite this recipient.
            if "invalidSharingRequest" in GoogleClient._get_error_reason(gsheets_err):
                print(
                    "gsheets invalidSharingRequest, retrying with sendNotificationEmail=True"
                )
                self.drive_service.permissions().create(
                    fileId=file_id,
                    body=user_permission,
                    fields="id",
                    # transferOwnership=True,  # For role=owner
                    # This will send a semi-ugly email from sheets@voxana.iam.gserviceaccount.com shared a spreadsheet
                    sendNotificationEmail=True,
                ).execute()
            else:
                raise gsheets_err

    def add_form_datas_to_spreadsheet(self, form_datas: List[FormData]):
        sheet_cache = {}

        for form_data in form_datas:
            form_name = form_data.form.form_name.value
            if form_name not in sheet_cache:
                sheet_cache[form_name] = get_or_create_worksheet(
                    self.spreadsheet, form_name
                )

            _add_form_data_to_sheet(sheet_cache[form_name], form_data)


def send_gsheets_shareable_link(account_id: uuid.UUID, shareable_link: str):
    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=account_id,
        idempotency_id=str(account_id),  # One shareable link for account (for now)
        subject="Your Voxana Spreadsheet - with all the data you enter at one place",
    )

    email_params.body_html = simple_email_body_html(
        title=email_params.subject,
        content_text="""
        <p>Hi, </p>
        <p>
            Click below to access your Voxana Spreadsheet
            - which will get automatically updated with each voice memo.
        </p>
        <p>{button_html}</p>
        """.format(
            button_html=button_template("Open in Google Sheets", shareable_link)
        ),
    )
    send_email(params=email_params)


def col_num_string(n):
    s = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        s = chr(65 + remainder) + s
    return s


# Function to update a row using a range
def update_row_with_range(sheet: Worksheet, row_number: int, values_list):
    col_letter = col_num_string(len(values_list))
    cell_range = f"A{row_number}:{col_letter}{row_number}"
    print(f"gsheets update_row_with_range row_number: {cell_range}")
    sheet.update(range_name=cell_range, values=[values_list])


def get_or_create_worksheet(spreadsheet, name: FormName):
    all_worksheets = spreadsheet.worksheets()

    # Try to find the worksheet with the given name
    worksheet = next((ws for ws in all_worksheets if ws.title == name), None)

    if worksheet is not None:
        return worksheet

    # If default "Sheet1" exists, rename it
    default_worksheet = all_worksheets[0]
    if default_worksheet.title == "Sheet1":
        print(f"gsheets get_or_create_worksheet update_title to {name}")
        default_worksheet.update_title(name)
        return default_worksheet

    # Otherwise, create a new worksheet with the given name
    print(f"gsheets get_or_create_worksheet add_worksheet title={name}")
    return spreadsheet.add_worksheet(title=name, rows="100", cols="26")


def _find_most_likely_header(
    sheet: Worksheet, labels: list, row_limit=10
) -> Tuple[int, Optional[list]]:
    most_matching_cols = 0
    most_matching_row = 0

    for row_num in range(1, row_limit + 1):
        row_values = sheet.row_values(row_num)
        matching_cols = len(set(row_values).intersection(set(labels)))

        if matching_cols > most_matching_cols:
            most_matching_cols = matching_cols
            most_matching_row = row_num

    existing_headers = (
        sheet.row_values(most_matching_row) if most_matching_row > 0 else None
    )
    print(
        f"gsheets _find_most_likely_header returned {most_matching_row} with existing_header {existing_headers}"
    )
    return most_matching_row, existing_headers


# The intent is to always fill in something relevant while NEVER messing with
# existing stuff. So the logic finds the corresponding columns, and appends a new row.
# This makes it stable against user renames, custom row appends.
def _add_form_data_to_sheet(sheet: Worksheet, form_data: FormData):
    data = form_data.to_display_tuples()
    labels = [d[0] for d in data]
    display_values = [d[1] for d in data]

    # Find most likely header row
    header_row_num, existing_headers = _find_most_likely_header(sheet, labels)

    # If the sheet is empty, make the header first row
    if header_row_num == 0:
        print("gsheets is empty, creating header with a row")
        # TODO(P0, ux): Create the fancy aggregates and stuff here.
        # NOTE: insert_row will create NEW rows and do NOT override stuff.
        sheet.insert_row(labels, 1)
        sheet.insert_row(display_values, 2)
        return

    # If headers exist, match keys and append data (this is a bit over-fancy)
    new_headers = []
    row_to_insert = []

    for label in labels:
        if label in existing_headers:
            col_idx = existing_headers.index(label) + 1
        else:
            # If a new header key, add a new column and set the value
            col_idx = len(existing_headers) + 1 + len(new_headers)
            print(f"gsheets add_form_data_to_sheet: adding new header {label}")
            new_headers.append(label)

        row_to_insert.append(col_idx)

    # Update new headers if any
    all_headers = existing_headers[:]
    if new_headers:
        start_col = len(existing_headers) + 1
        # The [[]] indicates empty columns
        sheet.insert_cols([[]] * len(new_headers), start_col)
        all_headers += new_headers
        update_row_with_range(sheet, row_number=header_row_num, values_list=all_headers)

    # Create a list of values to append based on the order of all headers (existing + new)
    label_values_map = {d[0]: d[1] for d in data}
    values_to_append = [label_values_map.get(header, "") for header in all_headers]

    # Insert a new row at index 2 (below the header row)
    sheet.insert_row(values_to_append, index=header_row_num + 1)

    print(f"gsheets: successfully added form_data; new_headers: {new_headers}")


# TODO: This would need some adjustments when people start doing multiple-entry for the same person


# ==== PROD SCRIPTS =====
def deduplicate(worksheet: Worksheet):
    rows = worksheet.get_all_values()
    header, rows = rows[0], rows[1:]
    orig_row_length = len(rows)
    print(f"gsheets deduplicating {orig_row_length} rows")

    try:
        name_col = header.index("Name")
        time_col = header.index("Recorded Time")
    except ValueError:
        raise Exception("Header does not contain 'Name' or 'Recording Time'.")

    deduped_dict = {}
    for row in rows:
        name = row[name_col]
        if name not in deduped_dict:
            deduped_dict[name] = row
        else:
            current_time_str = row[time_col]
            existing_time_str = deduped_dict[name][time_col]

            if current_time_str and existing_time_str:  # Both times exist
                # Assuming format is "%Y-%m-%d %H:%M %Z", then we can just compare the strings
                if current_time_str < existing_time_str:
                    deduped_dict[name][time_col] = current_time_str
            elif current_time_str:  # Only current time exists
                deduped_dict[name][time_col] = current_time_str

            for i, cell in enumerate(row):
                if (
                    len(cell) > len(deduped_dict[name][i])
                    or deduped_dict[name][i] == "None"
                ):
                    deduped_dict[name][i] = cell

    deduped_rows = list(deduped_dict.values())
    print(f"gsheets.deduplicated {orig_row_length} into {len(deduped_rows)} rows")
    worksheet.clear()
    worksheet.append_row(header)
    worksheet.append_rows(deduped_rows)


def _convert_date_format(old_date_str: str):
    # Try parsing the first format "Oct 24 2023, 2PM PDT"
    try:
        dt = datetime.strptime(old_date_str, "%b %d %Y, %I%p %Z")
        tz = pytz.timezone(dt.strftime("%Z"))
        dt = tz.localize(dt.replace(tzinfo=None))
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        pass

    # Try parsing the second format "2023-Oct-24 10:00 PDT"
    try:
        dt = datetime.strptime(old_date_str, "%Y-%b-%d %H:%M %Z")
        tz = pytz.timezone(dt.strftime("%Z"))
        dt = tz.localize(dt.replace(tzinfo=None))
        return dt.strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        print(f"WARNING: gsheets cannot convert {old_date_str}")
        return None


def convert_dates(worksheet: Worksheet, cell_range="A2:A100"):
    cells = worksheet.range(cell_range)
    print(f"gsheets gonna convert_dates for up to {len(cells)}")

    converted_count = 0
    for cell in cells:
        if cell.value:  # Check if cell is not empty
            orig_value = cell.value
            new_value = _convert_date_format(orig_value)
            if bool(new_value) and orig_value != new_value:
                converted_count += 1
                cell.value = new_value

    # Update the cells in batch
    worksheet.update_cells(cells)
    print(f"gsheets convert_dates converted {converted_count} cells")


TEST_FIELDS = [
    FieldDefinition(
        name="name",
        field_type="text",
        label="Name",
        description="Name of the person I talked with",
    ),
    FieldDefinition(
        name="role",
        field_type="text",
        label="Role",
        description="Current role or latest job experience",
    ),
    FieldDefinition(
        name="industry",
        field_type="text",
        label="Industry",
        description="which business area they specialize in professionally",
    ),
]


def test_gsheets():
    test_acc = Account.get_or_onboard_for_email(
        "peter+nogoogleaccount@voxana.ai", utm_source="test"
    )

    test_spreadsheet_name = f"Voxana Data Entry - Peter Csiba - {time.time()}"
    test_key = "10RbqaqCjB9qPZPUxE40FAs6t1zIveTUKRnSHhbIepis"
    # test_key = None
    # peter_key = "1-FyMc_W6d1PTuR4re5d5-uVowmgVWQtpEDjDsP1KplY"
    peter_key = None
    # katka_key = "1yB9tPcElKdBpDb-H0BbHjbTvuT0zSY--FIKsmnsvm_M"
    katka_key = None

    test_google_client = GoogleClient()
    test_google_client.login()

    # PROD SCRIPTS
    if bool(katka_key):
        print("working on katka's spreadsheet")
        test_google_client.open_by_key(katka_key)
        # katka_sheet = test_google_client.spreadsheet.get_worksheet(0)
        # deduplicate(katka_sheet)
        # convert_dates(katka_sheet, "B6:B196")
        exit()

    if bool(peter_key):
        print("working on peter's spreadsheet")
        test_google_client.open_by_key(peter_key)
        # peter_sheet = test_google_client.spreadsheet.get_worksheet(0)
        # convert_dates(peter_sheet, "A2:A245")
        # deduplicate(peter_sheet)
        # test_google_client.share_with("petherz@gmail.com")
        exit()

    # TEST
    if test_key is None:
        test_google_client.create(test_spreadsheet_name)
        test_google_client.share_with(test_acc)
        EmailLog.save_last_email_log_to("result-app-gsheets.html")
    else:
        test_google_client.open_by_key(test_key)

    test_form_data1 = FormData(
        FormDefinition(FormName.CONTACTS, TEST_FIELDS),
        {"name": "Peter Csiba", "role": "Swears a lot", "industry": "Tech-something"},
    )
    test_form_data2 = FormData(
        FormDefinition(FormName.CONTACTS, TEST_FIELDS),
        {"name": "Katka Sabo", "role": "I like to demo", "industry": "Business"},
    )
    test_form_data3 = FormData(
        FormDefinition(FormName.FOOD_LOG, FOOD_LOG_FIELDS),
        {"recording_time": "2023-10-23", "ingredient": "Rice", "activity": None},
    )
    test_google_client.add_form_datas_to_spreadsheet(
        [test_form_data1, test_form_data2, test_form_data3]
    )


if __name__ == "__main__":
    with connect_to_postgres(POSTGRES_LOGIN_URL_FROM_ENV):
        test_gsheets()
