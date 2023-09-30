import uuid
from typing import Optional

from database.models import BaseAccount, BaseOrganization, BasePipeline

ORGANIZATION_ROLE_CONTRIBUTOR = "contributor"
ORGANIZATION_ROLE_OWNER = "owner"


class Organization(BaseOrganization):
    class Meta:
        db_table = "organization"

    @staticmethod
    def get_or_create_for_account_id(
        account_id: uuid.UUID,
        name: str,
    ) -> "Organization":
        acc: BaseAccount = BaseAccount.get_by_id(account_id)
        organization: Optional[BaseOrganization] = BaseOrganization.get_or_none(
            BaseOrganization.id == acc.organization_id
        )
        if bool(organization):
            return organization

        print(f"creating new organization for owner account {account_id}")
        organization_id = BaseOrganization.insert(
            owner_account_id=account_id, name=name
        ).execute()
        print(f"updating account and becoming {ORGANIZATION_ROLE_OWNER}")
        acc.organization_id = organization_id
        acc.organization_role = ORGANIZATION_ROLE_OWNER
        acc.save()

        return BaseOrganization.get_by_id(organization_id)

    def get_oauth_data_id_for_destination(self, destination_id) -> uuid.UUID:
        pipeline: BasePipeline = BasePipeline.get(
            BasePipeline.organization_id == self.id
            and BasePipeline.destination_id == destination_id
        )
        return pipeline.oauth_data_id
