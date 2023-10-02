from database.models import BaseDataEntry

# TODO(P1, devx): Figure out enums like contact method
STATE_UPLOAD_INTENT = "upload_intent"
STATE_UPLOAD_DONE = "upload_done"
STATE_UPLOAD_TRANSCRIBED = "transcribed"  # processed_at


# TODO(P0, admin): Way to retry failed data-entries (or by id). Ideally should take less than an hour to implement
#   and somehow re-use the bucket-key url as we cannot rely on metadata.
class DataEntry(BaseDataEntry):
    class Meta:
        db_table = "data_entry"
