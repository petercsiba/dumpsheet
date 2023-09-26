import uuid
from typing import Optional

from database.models import BaseAccount, BaseOrganization

ORGANIZATION_ROLE_ADMIN = "admin"


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

        print(f"creating new organization for account {account_id}")
        organization_id = BaseOrganization.insert(name=name).execute()
        print("updating account and becoming admin")
        acc.organization_id = organization_id
        acc.organization_role = ORGANIZATION_ROLE_ADMIN
        acc.save()

        return BaseOrganization.get_by_id(organization_id)
