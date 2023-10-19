from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from gspread import Spreadsheet, Worksheet

from app.form import FieldDefinition, FormData, FormDefinition
from common.config import GOOGLE_FORMS_SERVICE_ACCOUNT_PRIVATE_KEY

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
        print(f"Created spreadsheet {spreadsheet_name} of {type(self.spreadsheet)}")

        return self.spreadsheet

    def open_by_key(self, spreadsheet_key) -> Optional[Spreadsheet]:
        if self.gspread_client is None:
            print("ERROR: Cannot open spreadsheet cause we didn't login")
            return None

        self.spreadsheet: Spreadsheet = self.gspread_client.open_by_key(spreadsheet_key)
        print(f"Opened spreadsheet {spreadsheet_key} of {type(self.spreadsheet)}")

        return self.spreadsheet

    def share_with(self, user_email):
        # Share spreadsheet
        file_id = self.spreadsheet.id
        print(f"INFO: Sharing spreadsheet {self.spreadsheet.id} with {user_email}")
        user_permission = {
            "type": "user",
            "role": "writer",
            # 'role': 'owner',  # TODO: would be nice to have the user as owner
            # Consent is required to transfer ownership of a file to another user.
            "emailAddress": user_email,
            # 'allowFileDiscovery': True  # allowFileDiscovery is not valid for individual users
        }
        self.drive_service.permissions().create(
            fileId=file_id,
            body=user_permission,
            fields="id",
            # transferOwnership=True,  # For role=owner
            sendNotificationEmail=True,  # TODO(P1, ux): This we should personalize
        ).execute()


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
    print(f"update_row_with_range row_number: {cell_range}")
    sheet.update(cell_range, [values_list])


def add_form_data_to_sheet(sheet: Worksheet, form_data: FormData):
    # Access the first row to get the headers
    existing_headers = sheet.row_values(1)

    # Your data dict, TODO: Use display values for fields.
    data_dict = form_data.to_dict()

    # If there are no headers, create one
    if not existing_headers:
        print("add_form_data_to_sheet: no headers, creating header with a row")
        # Set the headers to be the keys from the data_dict
        sheet.insert_row(list(data_dict.keys()), 1)
        # Insert the data
        sheet.insert_row(list(data_dict.values()), 2)
        return

    # If headers exist, match keys and append data (this is a bit over-fancy)
    new_headers = []
    row_to_insert = []

    for key in data_dict.keys():
        if key in existing_headers:
            col_idx = existing_headers.index(key) + 1
        else:
            # If a new header key, add a new column and set the value
            col_idx = len(existing_headers) + 1 + len(new_headers)
            print(f"add_form_data_to_sheet: adding new header {key}")
            new_headers.append(key)

        row_to_insert.append(col_idx)

    # Update new headers if any
    all_headers = existing_headers[:]
    if new_headers:
        start_col = len(existing_headers) + 1
        # The [[]] indicates empty columns
        sheet.insert_cols([[]] * len(new_headers), start_col)
        all_headers += new_headers
        update_row_with_range(sheet, 1, all_headers)

    # Create a list of values to append based on the order of all headers (existing + new)
    values_to_append = [data_dict.get(header, "") for header in all_headers]

    # Append the new row
    sheet.append_row(values_to_append)


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


if __name__ == "__main__":
    name = "Voxana - Peter Csiba - Networking Dump"

    test_key = "10RbqaqCjB9qPZPUxE40FAs6t1zIveTUKRnSHhbIepis"

    test_google_client = GoogleClient()
    test_google_client.login()
    if test_key is None:
        new_spreadsheet = test_google_client.create(name)
        key = new_spreadsheet.id
        test_google_client.share_with("petherz@gmail.com")
    else:
        test_google_client.open_by_key(test_key)

    test_sheet = test_google_client.spreadsheet.sheet1

    test_form_data1 = FormData(
        FormDefinition(TEST_FIELDS),
        {"name": "Peter Csiba", "role": "Swears a lot", "industry": "Tech-something"},
    )
    add_form_data_to_sheet(test_sheet, test_form_data1)

    test_form_data2 = FormData(
        FormDefinition(TEST_FIELDS),
        {"name": "Katka Sabo", "role": "I like to demo", "industry": "Business"},
    )
    add_form_data_to_sheet(test_sheet, test_form_data2)
