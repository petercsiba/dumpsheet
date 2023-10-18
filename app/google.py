import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

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
class Spreadsheet:
    def __init__(self, header: list[str]):
        self.header = header
        self.gspread_client = None
        self.drive_service = None
        self.spreadsheet = None

    def login(self):
        # Initialize API
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        credentials = Credentials.from_service_account_info(
            _google_credentials_json, scopes=scopes
        )
        print("Login to google services")
        self.gspread_client = gspread.authorize(credentials)
        self.drive_service = build("drive", "v3", credentials=credentials)

    def create(self, spreadsheet_name):
        self.spreadsheet = self.gspread_client.create(spreadsheet_name)
        print(f"Created spreadsheet {spreadsheet_name}")

        # Open the spreadsheet
        sheet = self.spreadsheet.sheet1
        # TODO: Add header
        # Add a row
        sheet.append_row(["New", "Row", "Data"])
        # Update a cell
        sheet.update_cell(2, 2, "Modified Data")

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


name = "Voxana - Peter Csiba - Networking Dump"

s = Spreadsheet(["first column"])
s.login()
s.create(name)
s.share_with("petherz@gmail.com")
