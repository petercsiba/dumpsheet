import uuid
from typing import Optional

from database.models import BasePipeline
from database.oauth_data import OauthData
from database.organization import Organization

STATE_INITIATED = "initiated"


class Pipeline(BasePipeline):
    class Meta:
        db_table = "pipeline"

    @staticmethod
    def get_or_create_for_destination_as_admin(
        admin_account_id: Optional[uuid.UUID],
        destination_id: int,
        org_name: str,
    ) -> "Pipeline":
        org: Organization = Organization.get_or_create_for_account_id(
            admin_account_id, org_name
        )
        pipeline = Pipeline.get_or_create_for(
            organization_id=org.id, destination_id=destination_id
        )
        pipeline.oauth_data_id = OauthData.create_placeholder()
        pipeline.save()
        return pipeline

    @staticmethod
    def get_or_create_for(organization_id: uuid.UUID, destination_id: int):
        pipeline: Pipeline = Pipeline.get_or_none_by_org_dest(
            organization_id, destination_id
        )
        if pipeline is None:
            pipeline_id = Pipeline.insert(
                organization_id=organization_id,
                destination_id=destination_id,
                # owner_id=admin_account_id,
                state=STATE_INITIATED,
            ).execute()
            pipeline = Pipeline.get_by_id(pipeline_id)

        return pipeline

    @staticmethod
    def get_or_none_by_org_dest(
        organization_id: uuid, destination_id: int
    ) -> "Pipeline":
        return BasePipeline.get_or_none(
            BasePipeline.organization_id == organization_id
            and BasePipeline.destination_id == destination_id
        )
