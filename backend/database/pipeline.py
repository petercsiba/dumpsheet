import uuid

from database.models import BasePipeline

STATE_INITIATED = "initiated"


class Pipeline(BasePipeline):
    class Meta:
        table_name = "pipeline"

    @staticmethod
    def get_or_none_for_org_id(org_id: str, destination_id: int) -> "Pipeline":
        return Pipeline.get_or_none(
            Pipeline.organization_id == org_id
            and Pipeline.destination_id == destination_id
        )

    @staticmethod
    def get_or_none_for_external_org_id(
        external_org_id: str, destination_id: int
    ) -> "Pipeline":
        return Pipeline.get_or_none(
            Pipeline.external_org_id == external_org_id
            and Pipeline.destination_id == destination_id
        )

    @staticmethod
    def get_or_create_for(
        external_org_id: str, organization_id: uuid.UUID, destination_id: int
    ):
        existing_pipeline = Pipeline.get_or_none_for_external_org_id(
            external_org_id, destination_id
        )
        if bool(existing_pipeline):
            print(f"Pipeline already exists: {existing_pipeline}")
            return existing_pipeline

        print(
            f"Creating Pipeline between organization {organization_id} and destination {destination_id}"
        )
        pipeline_id = Pipeline.insert(
            external_org_id=external_org_id,
            organization_id=organization_id,
            destination_id=destination_id,
            state=STATE_INITIATED,
        ).execute()

        return Pipeline.get_by_id(pipeline_id)
