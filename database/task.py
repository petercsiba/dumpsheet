import datetime
import json
import uuid

from database.models import BaseTask

TASK_INITIATED = "initiated"
TASK_DONE = "done"
TASK_TERMINATED = "terminated"

# Feels like "app.result"
KEY_HUBSPOT_CONTACT = "hubspot_contact"
KEY_HUBSPOT_CALL = "hubspot_call"
KEY_HUBSPOT_TASK = "hubspot_task"
KEY_NETWORKING_DRAFT = "networking_draft"


def _is_json_serializable(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


# Convert common types
def _datetime_converter(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _datetime_converter(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_datetime_converter(element) for element in obj]
    else:
        return obj


# Retains data from the done transcription -> action performed.
# -- in the ETL world usually encompasses all of Task, Logs (Events) and Audit Trail (History).
# Currently, the primary use case is for debugging rather than consistency, so things might be a bit messy here.
class Task(BaseTask):
    class Meta:
        db_table = "task"

    @staticmethod
    def create_task(data_entry_id: uuid.UUID, pipeline_id: int) -> "Task":
        task_id = Task.insert(
            data_entry_id=data_entry_id, pipeline_id=pipeline_id
        ).execute()
        task = Task.get_by_id(task_id)
        return task

    # Here "output" means "draft" in user-facing output,
    # one Task can handle multiple results.
    # `output` should be JSON serializable
    def add_generated_output(self, key: str, output):
        if self.state != TASK_INITIATED:
            print(
                f"WARNING: trying to add_generated_output for non-initiated task {self.state}"
            )

        output = _datetime_converter(output)
        if not _is_json_serializable(output):
            print(
                f"ERROR: generated output ain't json serializable (type {type(output)}), converting to str"
            )
            output = str(output)

        print(f"TASK {self.id} {key}: add_generated_output")
        if self.drafted_output is None:
            self.drafted_output = []

        self.drafted_output.append(
            {
                "key": key,
                "output": output,
            }
        )
        self.save()

    # When syncing to external systems.
    # `response` should be JSON serializable
    def add_sync_response(self, key: str, status: str, response, is_finished=False):
        if self.state != TASK_INITIATED:
            print(
                f"WARNING: trying to add_sync_response for non-initiated task {self.state}"
            )

        response = _datetime_converter(response)
        if not _is_json_serializable(response):
            print(
                f"ERROR: generated output ain't json serializable (type {type(response)}), converting to str"
            )
            response = str(response)

        print(f"TASK {self.id} {key}: add_sync_response status = {status}")
        if self.api_response is None:
            self.api_response = []

        self.api_response.append(
            {
                "key": key,
                "status": status,
                "response": response,
            }
        )

        if is_finished:
            self.state = TASK_DONE

        self.save()

    def finish(self):
        self.state = TASK_DONE
        self.save()

    def terminate(self):
        self.state = TASK_TERMINATED
        self.save()
