import json
import re
import time
from datetime import datetime
from typing import List, Optional, Tuple

import gspread
import pytz
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from gspread import Client, Spreadsheet, Worksheet, utils
from gspread.utils import rowcol_to_a1
from gspread_formatting import (
    ConditionalFormatRule,
    ConditionalFormatRules,
    get_conditional_format_rules,
)

from app.email_template import button_snippet_for_spreadsheet, simple_email_body_html
from app.emails import send_email
from app.form_library import FOOD_LOG_FIELDS, get_form
from app.gsheets_view import get_overlay_cell_format
from common.config import GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY
from common.form import FormData, FormDefinition, FormName
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


# https://docs.google.com/spreadsheets/d/1cF1INs_VErKmTGgCJJ20YjbL-2ZBFQtiN9ZeNlJxBLE/edit#gid=627329407
TEMPLATE_CONTACTS_SPREADSHEET_ID = "1cF1INs_VErKmTGgCJJ20YjbL-2ZBFQtiN9ZeNlJxBLE"


# Bit hacky as it is responsible for both authorization with Google API, AND managing the spreadsheet itself.
# Stateful.
# Some errors to share to set expectations:
# * gspread.exceptions.APIError: {'code': 400, 'message': 'Range (Sheet1!A1003) exceeds grid limits.
#                                 Max rows: 1002, max columns: 26', 'status': 'INVALID_ARGUMENT'}
class GoogleClient:
    def __init__(self):
        # The 3rd party library providing python-ic abstraction on top-of the Google API.
        self.gspread_client: Optional[Client] = None
        # Compared to gspread_client a lower-level client on the HTTP abstraction level,
        # has more capabilities but harder to work with.
        self.sheets_service = None
        self.drive_service = None
        # Current spreadsheet that we are working on
        self.spreadsheet: Optional[Spreadsheet] = None

    def login(self):
        # Initialize API
        # We do it explicitly here, so we don't have to deal with materializing the json file
        # gc = gspread.service_account(filename='path/to/service_account.json')
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            credentials = Credentials.from_service_account_info(
                _google_credentials_json, scopes=scopes
            )
            # TODO(P1, devx/ux): Lazy load these
            print("Login to google services")
            self.gspread_client = gspread.authorize(credentials)
            self.sheets_service = build("sheets", "v4", credentials=credentials)
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

    def copy_from(self, template_spreadsheet_id: str, new_name) -> Spreadsheet:
        print("gsheets copy_from template_spreadsheet_id")
        request = self.drive_service.files().copy(fileId=template_spreadsheet_id)
        response = request.execute()
        new_spreadsheet_id = response["id"]
        print(
            f"gsheets copy_from success {template_spreadsheet_id} -> {new_spreadsheet_id}"
        )

        # Rename the new spreadsheet using Drive API
        rename_request = self.drive_service.files().update(
            fileId=new_spreadsheet_id, body={"name": new_name}
        )
        rename_request.execute()

        return self.open_by_key(response["id"])

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
        print(f"gsheets share_with acc {acc.id} and spreadsheet {self.spreadsheet.id}")
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

            send_gsheets_shareable_link(acc=acc)

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

    @staticmethod
    def _delete_me_rows(worksheet: Worksheet):
        print(f"gsheets _delete_me_rows for {worksheet.title}")

        # Find all occurrences of 'delete me' (case-insensitive)
        cells = worksheet.findall("__delete_me__")

        # Get the unique list just to be sure
        rows_to_delete = list(set([cell.row for cell in cells]))

        # Delete rows in reverse to avoid shifting indices
        for row_index in sorted(rows_to_delete, reverse=True):
            print(f"gsheets _delete_me_rows deleting row {row_index}")
            worksheet.delete_rows(start_index=row_index)

    def add_form_datas_to_spreadsheet(self, form_datas: List[FormData]):
        if form_datas is None or len(form_datas) == 0:
            print("WARNING gsheets add_form_datas_to_spreadsheet empty form_datas")
            return

        sheet_cache = {}

        for form_data in form_datas:
            form_name = form_data.form.form_name.value
            if form_name not in sheet_cache:
                sheet_cache[form_name] = get_or_create_worksheet(
                    self.spreadsheet, form_name
                )
            # NOTE: A much better way is that you use B6:B200 instead of $B6:$B200,
            #   the first one stays, the other is shifted.
            _add_form_data_to_sheet(sheet_cache[form_name], form_data)
            # For "plain" worksheets we skip this
            # if header_row_index > 1:
            #     self.update_formulas(
            #         worksheet_title=sheet_cache[form_name].title,
            #         cell_range=f"A1:Z{header_row_index-1}",
            #         start_row_index=header_row_index + 1,
            #     )

        # TODO(hack): This is to delete extra rows copied from the Template spreadsheet used as a style guidance
        #   for the first data row inserted.
        for _, sheet in sheet_cache.items():
            GoogleClient._delete_me_rows(sheet)

        # For some conditional formatting we might need to re-apply all the rules. Before doing that, we
        # should check if our rules are right or not (e.g. empty <> FALSE <> 'FALSE).
        # self.refresh_conditional_formatting_on_all_sheets()

    # Documentation: half of https://chat.openai.com/share/fc19b2b0-4bd9-4c8d-9e18-5bf59f77d702
    # NOTE: A much better way is that you use B6:B200 instead of $B6:$B200, the first one stays, the other is shifted.
    def update_formulas(self, worksheet_title, cell_range, start_row_index: int):
        range_name = f"{worksheet_title}!{cell_range}"
        print(
            f"gsheets update_formulas for {range_name} start_row_index {start_row_index}"
        )

        def replacer(match):
            start_col = match.group(1)
            start_row = int(match.group(2))
            range_colon = match.group(3)
            end_col = match.group(4)
            end_row = match.group(5)

            print(f"match replacer {start_row}, {range_colon}, {end_row}")

            updated_start_row = min(start_row, start_row_index)

            # If it's a range, keep the end row as is
            if range_colon:
                return f"{start_col}{updated_start_row}:{end_col}{end_row}"
            else:
                return f"{start_col}{updated_start_row}"

        # Fetch cells with formulas
        result = (
            self.sheets_service.spreadsheets()
            .values()
            .batchGet(
                spreadsheetId=self.spreadsheet.id,
                ranges=[range_name],  # contains worksheet name
                valueRenderOption="FORMULA",
            )
            .execute()
        )

        pattern = re.compile(r"(\$?[A-Z]+\$?)(\d+)(:?)(\$?[A-Z]*\$?)(\d*)")
        cells_to_update = []

        for value_range in result["valueRanges"]:
            values = value_range["values"]
            for row_idx, row in enumerate(values):
                for col_idx, cell in enumerate(row):
                    if cell.startswith("="):
                        new_formula = re.sub(pattern, replacer, cell)
                        if new_formula != cell:
                            print(f"gsheets update_formulas {cell} -> {new_formula}")
                            cells_to_update.append(
                                {
                                    "range": f"{worksheet_title}!{utils.rowcol_to_a1(row_idx + 1, col_idx + 1)}",
                                    "values": [[new_formula]],
                                }
                            )

        # Update cells with new formulas
        if len(cells_to_update) > 0:
            # NOTE: This should also re-calculate the formula, but I am unsure if it does after insert_row.
            self.sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet.id,
                body={"data": cells_to_update, "valueInputOption": "USER_ENTERED"},
            ).execute()

        print(f"gsheets update_formulas total updated {len(cells_to_update)}")

    # TODO: Add parameters if we ever gonna use it - this is now for checkboxes.
    def add_conditional_formatting(self):
        print("gsheets add_conditional_formatting")
        # Define the conditional formatting rule
        request_body = {
            "requests": [
                {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [
                                {
                                    "sheetId": self.spreadsheet.worksheets()[0].id,
                                    "startRowIndex": 5,
                                    "endRowIndex": 200,
                                    "startColumnIndex": 1,
                                    "endColumnIndex": 2,
                                }
                            ],
                            "booleanRule": {
                                "condition": {
                                    "type": "CUSTOM_FORMULA",
                                    "values": [{"userEnteredValue": "=B6=TRUE"}],
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": 0.0,
                                        "green": 1.0,
                                        "blue": 0.0,
                                    }
                                },
                            },
                        },
                        "index": 0,
                    }
                }
            ]
        }

        # Send the request to add the conditional formatting rule
        return (
            self.sheets_service.spreadsheets()
            .batchUpdate(spreadsheetId=self.spreadsheet.id, body=request_body)
            .execute()
        )

    def refresh_conditional_formatting_on_all_sheets(self):
        # Loop through each worksheet in the spreadsheet
        for worksheet in self.spreadsheet.worksheets():
            GoogleClient.refresh_conditional_formatting(worksheet)

    # The intent of this function was to re-apply all conditional formatting on the spreadsheet,
    # BUT even though we logically do it, the UI does NOT pick it up.
    @staticmethod
    def refresh_conditional_formatting(worksheet: Worksheet):
        print(f"gsheets refresh_conditional_formatting on worksheet {worksheet.title})")

        # Fetch all existing rules
        rules_obj: ConditionalFormatRules = get_conditional_format_rules(worksheet)
        saved_rules: list[ConditionalFormatRule] = rules_obj.rules.copy()
        if len(saved_rules) == 0:
            print(
                f"gsheets refresh_conditional_formatting skipping worksheet {worksheet.title} as no rules"
            )
            return

        # Clear existing rules
        rules_obj.clear()
        rules_obj.save()

        # Reapply saved rules
        for saved_rule in saved_rules:
            # WTF please, don't even ask, this took me well above an hour to figure out.
            # Somehow the Google API response value can NOT be used in the Google API request :/
            # I.e. it returns NUMBER_EQ == TRUE, but it only takes CUSTOM_FORMULA
            condition = saved_rule.booleanRule.condition
            if condition.type == "NUMBER_EQ":
                for i, value in enumerate(condition.values):
                    if value.userEnteredValue in ["FALSE", "TRUE"]:
                        condition.type = "CUSTOM_FORMULA"
                        grid_range = saved_rule.ranges[0]
                        first_cell_a1 = rowcol_to_a1(
                            grid_range.startRowIndex + 1,
                            grid_range.startColumnIndex + 1,
                        )
                        new_rule = f"={first_cell_a1}={value.userEnteredValue}"
                        print(
                            f"gsheets refresh_conditional_formatting updating rule to {new_rule}"
                        )
                        condition.values[i].userEnteredValue = new_rule
                        break

            # rules_obj.rules.append(saved_rule)
            rules_obj.insert(0, saved_rule)
            try:
                rules_obj.save()
            except Exception as e:
                print(f"ERROR: Failed to apply rule: {saved_rule} cause {e}")

    def get_worksheet_title(self, index=0):
        # index=0 is guaranteed to exist
        worksheet: Worksheet = self.spreadsheet.worksheets()[index]
        return worksheet.title

    # Documentation: https://chat.openai.com/share/5967ea0a-3d56-40c0-8735-92b1f65d12fa
    def get_all_unique_cell_formats(self, cell_range="A1:Z10") -> List[dict]:
        sheet_range = f"{self.get_worksheet_title()}!{cell_range}"
        print(
            f"gsheets get_all_unique_cell_formats for range {sheet_range} in {self.spreadsheet.id}"
        )

        # We use sheets_service over gspread_client cause it allows us to get the formatting information in batch
        request = self.sheets_service.spreadsheets().get(
            spreadsheetId=self.spreadsheet.id,
            ranges=sheet_range,
            fields="sheets.data.rowData.values.effectiveFormat",
        )
        response = request.execute()

        # Initialize set to store unique formats
        unique_formats = set()

        # Loop through the rows and cells to get unique formats
        for sheet in response["sheets"]:
            for row in sheet["data"][0]["rowData"]:
                for cell in row["values"]:
                    if "effectiveFormat" in cell:
                        # Convert to a json string representation so it's hashable for the unique set
                        unique_format = json.dumps(
                            cell["effectiveFormat"], sort_keys=True
                        )
                        unique_formats.add(unique_format)

        # Convert back to dict for later use if needed
        return [json.loads(s) for s in unique_formats]

    # NOTE: Conditional formatting rules are on the spreadsheet level and have go be applied
    # with somewhat weird rules (and not for each cell).
    def get_all_unique_conditional_formats(self) -> List[dict]:
        print(
            f"gsheets get_all_unique_conditional_formats in spreadsheet {self.spreadsheet.id}"
        )
        request = self.sheets_service.spreadsheets().get(
            spreadsheetId=self.spreadsheet.id, fields="sheets.conditionalFormats"
        )

        response = request.execute()

        # Collect unique conditional formats
        unique_conditional_formats = set()
        for sheet in response["sheets"]:
            if "conditionalFormats" in sheet:
                for conditional_format in sheet["conditionalFormats"]:
                    unique_str = json.dumps(conditional_format, sort_keys=True)
                    unique_conditional_formats.add(unique_str)

        return [json.loads(s) for s in unique_conditional_formats]


def send_gsheets_shareable_link(acc: Account):
    shareable_link = acc.get_shareable_spreadsheet_link()
    if shareable_link:
        return None

    email_params = EmailLog.get_email_reply_params_for_account_id(
        account_id=acc.id,
        idempotency_id=str(acc.id),  # One shareable link for account (for now)
        subject="Your Voxana Spreadsheet - with all the data you enter at one place",
    )

    email_params.body_html = simple_email_body_html(
        title=email_params.subject,
        content_text="""
        <p>Hi boss, </p>
        <p>
            Click below to access your Voxana Spreadsheet
            - which will get automatically updated with each voice memo.
        </p>
        <p>{button_html}</p>
        """.format(
            button_html=button_snippet_for_spreadsheet(shareable_link)
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

    # TODO(P0, reliability): Bump the limit in GCP, handle retries gracefully.
    # {'code': 429, 'message': "Quota exceeded for quota metric 'Read requests' and limit
    #   'Read requests per minute per user' of service}
    #  'reason': 'RATE_LIMIT_EXCEEDED'
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
def _add_form_data_to_sheet(sheet: Worksheet, form_data: FormData) -> int:
    data = form_data.to_display_tuples()
    labels = [d[0] for d in data]
    # TODO(P0, ux): Use FieldDefinition.field_type information to format individual cells.
    display_values = [d[1] for d in data]

    # Find most likely header row
    header_row_num, existing_headers = _find_most_likely_header(sheet, labels)

    # If the sheet is empty, make the header first row
    if header_row_num == 0:
        print("gsheets is empty, creating header with a row")
        # NOTE: insert_row will create NEW rows and does NOT override stuff.
        sheet.insert_row(labels, 1)
        sheet.insert_row(display_values, 2)
        return 1

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

    # Insert a new row below the header row
    new_row_index = header_row_num + 1
    sheet.insert_row(values_to_append, index=new_row_index)

    print(f"gsheets: successfully added form_data; new_headers: {new_headers}")
    return header_row_num


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


def test_gsheets():
    test_acc = Account.get_or_onboard_for_email(
        "peter@voxana.ai", utm_source="test", full_name="Peter Csiba"
    )

    test_spreadsheet_name = f"Voxana Data Entry - Peter Csiba - {time.time()}"
    # test_key = "10RbqaqCjB9qPZPUxE40FAs6t1zIveTUKRnSHhbIepis"
    test_key = None
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
        unique_formats = test_google_client.get_all_unique_cell_formats(
            cell_range="B6:C10"
        )
        overlay_formats = []
        for uf in unique_formats:
            base, diff = get_overlay_cell_format(uf)
            overlay_formats.append(diff)
        # print(json.dumps(overlay_formats, indent=4))

        unique_conditional_formats = (
            test_google_client.get_all_unique_conditional_formats()
        )
        print(json.dumps(unique_conditional_formats, indent=4))

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
        # test_google_client.create(test_spreadsheet_name)
        test_google_client.copy_from(
            TEMPLATE_CONTACTS_SPREADSHEET_ID, test_spreadsheet_name
        )
        test_google_client.share_with(test_acc)
        EmailLog.save_last_email_log_to("result-app-gsheets.html")
    else:
        test_google_client.open_by_key(test_key)

    test_form_data1 = FormData(
        get_form(FormName.CONTACTS),
        {
            "recording_time": datetime.now(),
            "name": "Peter Csiba",
            "role": "Swears a lot",
            "industry": "Tech-something",
        },
    )
    test_form_data2 = FormData(
        get_form(FormName.CONTACTS),
        {
            "recording_time": datetime.now(),
            "name": "Katka Sabo",
            "role": "I like to demo",
            "industry": "Business",
        },
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
