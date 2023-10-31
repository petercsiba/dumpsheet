import datetime
import uuid

from app import utils
from common.form import FormData
from database.models import BaseTask

TASK_INITIATED = "initiated"
TASK_DONE = "done"
TASK_TERMINATED = "terminated"

# Feels like "app.result"
KEY_HUBSPOT_CONTACT = "hubspot_contact"
KEY_HUBSPOT_CALL = "hubspot_call"
KEY_HUBSPOT_TASK = "hubspot_task"


# Retains data from the done transcription -> action performed.
# -- in the ETL world usually encompasses all the Task, Logs (Events) and Audit Trail (History).
# NOTE: Currently, we are still figuring out the best structure.
# The primary use case is for debugging rather than consistency, so things might be a bit messy here.
class Task(BaseTask):
    class Meta:
        db_table = "task"

    @staticmethod
    def create_task(workflow_name: str, data_entry_id: uuid.UUID) -> "Task":
        # TODO(P2, devx): Update some field so we know it's a re-run, although timestamps would tell that.
        task_id = (
            Task.insert(workflow_name=workflow_name, data_entry_id=data_entry_id)
            .on_conflict_ignore()
            .execute()
        )

        task = Task.get_by_id(task_id)
        return task

    # NOTE: This is somewhat redundant to PromptLog - but here we only collect final user-visible outputs.
    # Here "output" means "draft" in user-facing output,
    # one Task can handle multiple results.
    # `output` should be JSON serializable
    # `key` does not need to be unique.
    def add_generated_output(self, key: str, form_data: FormData):
        if self.state != TASK_INITIATED:
            print(
                f"WARNING: trying to add_generated_output for non-initiated task {self.state}"
            )

        output = utils.to_json_serializable(form_data.to_dict())

        print(f"TASK {self.id} {key}: add_generated_output")
        if self.drafted_output is None:
            self.drafted_output = []

        self.drafted_output.append(
            {
                "key": key,
                "output": output,
                "timestamp": datetime.datetime.now().isoformat(),  # for json serializable
            }
        )
        self.save()

    # When syncing to external systems.
    # `response` should be JSON serializable
    def add_sync_response(
        self, key: str, status: str, response: dict, is_finished=False
    ):
        if self.state != TASK_INITIATED:
            print(
                f"WARNING: trying to add_sync_response for non-initiated task {self.state}"
            )

        response = utils.to_json_serializable(response)

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
