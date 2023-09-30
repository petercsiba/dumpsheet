import datetime
import uuid
from typing import Optional

from database.models import BaseOauthData


class OauthData(BaseOauthData):
    class Meta:
        db_table = "oauth_data"

    @staticmethod
    def create_placeholder(token_type="oauth"):
        return BaseOauthData.insert(token_type=token_type).execute()

    # @input: `tokens` is to be expected a valid response from HubSpot().auth.oauth.tokens_api.create
    @staticmethod
    def update_safely(
        oauth_data_id: uuid.UUID,
        refresh_token: str,
        access_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> uuid.UUID:
        try:
            # True for at least HubSpot
            uuid.UUID(str(refresh_token))
        except Exception as e:
            print(
                f"WARNING: expected refresh_token to be an UUID, got {type(refresh_token)}: {e}"
            )

        now = datetime.datetime.now()
        expires_at = None
        if bool(expires_in):
            expires_at = now + datetime.timedelta(seconds=expires_in - 60)

        oauth_data = BaseOauthData.get_by_id(oauth_data_id)
        oauth_data.refresh_token = refresh_token
        oauth_data.access_token = access_token
        oauth_data.expires_at = expires_at
        oauth_data.save()

        print(
            f"Success updated oath token with id {oauth_data_id}, good until expires at {expires_at}"
        )
        return oauth_data
