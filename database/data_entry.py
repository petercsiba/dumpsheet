from database.models import BaseDataEntry

# TODO(P1, devx): Figure out enums like contact method
STATE_UPLOAD_INTENT = "upload_intent"
STATE_UPLOAD_DONE = "upload_done"
STATE_UPLOAD_TRANSCRIBED = "transcribed"  # processed_at


class DataEntry(BaseDataEntry):
    class Meta:
        db_table = "data_entry"
