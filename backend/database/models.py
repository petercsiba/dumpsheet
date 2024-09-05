from peewee import *
from playhouse.postgres_ext import *

# NOTE: this file is fully generated, if you change something, it will go away
# database_proxy is an abstraction around PostgresqlDatabase so we can defer initialization after model
# declaration (i.e. the BaseDatabaseModels don't need to import that heavy object).
from supawee.client import database_proxy


class UnknownField(object):
    def __init__(self, *_, **__):
        pass


class BaseDatabaseModel(Model):
    class Meta:
        database = database_proxy


class BaseOrganization(BaseDatabaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    name = TextField()

    class Meta:
        schema = "public"
        table_name = "organization"


class BaseUsers(BaseDatabaseModel):
    aud = CharField(null=True)
    banned_until = DateTimeField(null=True)
    confirmation_sent_at = DateTimeField(null=True)
    confirmation_token = CharField(null=True)
    confirmed_at = DateTimeField(null=True)
    created_at = DateTimeField(null=True)
    deleted_at = DateTimeField(null=True)
    email = CharField(null=True)
    email_change = CharField(null=True)
    email_change_confirm_status = SmallIntegerField(null=True)
    email_change_sent_at = DateTimeField(null=True)
    email_change_token_current = CharField(null=True)
    email_change_token_new = CharField(null=True)
    email_confirmed_at = DateTimeField(null=True)
    encrypted_password = CharField(null=True)
    id = UUIDField(null=True)
    instance_id = UUIDField(null=True)
    invited_at = DateTimeField(null=True)
    is_anonymous = BooleanField(null=True)
    is_sso_user = BooleanField(null=True)
    is_super_admin = BooleanField(null=True)
    last_sign_in_at = DateTimeField(null=True)
    phone = TextField(null=True)
    phone_change = TextField(null=True)
    phone_change_sent_at = DateTimeField(null=True)
    phone_change_token = CharField(null=True)
    phone_confirmed_at = DateTimeField(null=True)
    raw_app_meta_data = BinaryJSONField(null=True)
    raw_user_meta_data = BinaryJSONField(null=True)
    reauthentication_sent_at = DateTimeField(null=True)
    reauthentication_token = CharField(null=True)
    recovery_sent_at = DateTimeField(null=True)
    recovery_token = CharField(null=True)
    role = CharField(null=True)
    updated_at = DateTimeField(null=True)

    class Meta:
        schema = "auth"
        table_name = "users"
        primary_key = False


class BaseAccount(BaseDatabaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    full_name = TextField(null=True)
    gsheet_id = TextField(null=True, unique=True)
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    # To overcome ForeignKeyField circular dependency
    merged_into_id = UUIDField(null=True)
    organization = ForeignKeyField(
        column_name="organization_id", field="id", model=BaseOrganization, null=True
    )
    organization_role = TextField(null=True)
    organization_user_id = TextField(null=True)
    state = TextField(constraints=[SQL("DEFAULT 'active'::text")])
    user = ForeignKeyField(
        column_name="user_id", field="id", model=BaseUsers, null=True
    )

    class Meta:
        schema = "public"
        table_name = "account"


class BaseDataEntry(BaseDatabaseModel):
    account = ForeignKeyField(
        column_name="account_id", field="id", model=BaseAccount, null=True
    )
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    display_name = TextField()
    id = UUIDField(constraints=[SQL("DEFAULT uuid_generate_v4()")], primary_key=True)
    idempotency_id = TextField(unique=True)
    input_type = TextField()
    input_uri = TextField(null=True)
    output_transcript = TextField(null=True)
    processed_at = DateTimeField(null=True)
    state = TextField(constraints=[SQL("DEFAULT 'upload_intent'::text")])

    class Meta:
        schema = "public"
        table_name = "data_entry"


class BaseDestination(BaseDatabaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
    id = BigAutoField()
    install_url = TextField(null=True)
    name = TextField()
    setup_info_url = TextField(null=True)

    class Meta:
        schema = "public"
        table_name = "destination"


class BaseEmailLog(BaseDatabaseModel):
    account = ForeignKeyField(
        column_name="account_id", field="id", model=BaseAccount, null=True
    )
    attachment_paths = ArrayField(
        constraints=[SQL("DEFAULT '{}'::text[]")], field_class=TextField
    )
    bcc = ArrayField(constraints=[SQL("DEFAULT '{}'::text[]")], field_class=TextField)
    body_html = TextField(null=True)
    body_text = TextField(null=True)
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = BigAutoField()
    idempotency_id = TextField()
    recipient = TextField()
    recipient_full_name = TextField(null=True)
    reply_to = TextField()
    sender = TextField()
    subject = TextField()

    class Meta:
        schema = "public"
        table_name = "email_log"
        indexes = ((("recipient", "idempotency_id"), True),)


class BaseOauthData(BaseDatabaseModel):
    access_token = TextField(null=True)
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    expires_at = DateTimeField(null=True)
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    refresh_token = TextField(null=True)
    refreshed_at = DateTimeField(null=True)
    token_type = TextField()

    class Meta:
        schema = "public"
        table_name = "oauth_data"


class BaseOnboarding(BaseDatabaseModel):
    account = ForeignKeyField(
        column_name="account_id", field="id", model=BaseAccount, null=True
    )
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    email = TextField(null=True)
    id = BigAutoField()
    ip_address = TextField(null=True)
    phone = TextField(null=True, unique=True)
    phone_carrier_info = TextField(null=True)
    referer = TextField(null=True)
    utm_source = TextField(null=True)

    class Meta:
        schema = "public"
        table_name = "onboarding"
        indexes = ((("ip_address", "email"), True),)


class BasePipeline(BaseDatabaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)
    destination = ForeignKeyField(
        column_name="destination_id", field="id", model=BaseDestination
    )
    external_org_id = TextField(null=True)
    id = BigAutoField()
    oauth_data = ForeignKeyField(
        column_name="oauth_data_id", field="id", model=BaseOauthData, null=True
    )
    organization = ForeignKeyField(
        column_name="organization_id", field="id", model=BaseOrganization
    )
    state = TextField(constraints=[SQL("DEFAULT 'initiated'::text")])

    class Meta:
        schema = "public"
        table_name = "pipeline"
        indexes = (
            (("external_org_id", "destination"), True),
            (("organization", "destination"), True),
        )


class BaseTask(BaseDatabaseModel):
    api_response = JSONField(null=True)
    code_version = TextField(null=True)
    created_at = DateTimeField(
        constraints=[SQL("DEFAULT (now() AT TIME ZONE 'utc'::text)")]
    )
    data_entry = ForeignKeyField(
        column_name="data_entry_id", field="id", model=BaseDataEntry
    )
    drafted_output = JSONField(null=True)
    id = BigAutoField()
    retries_count = BigIntegerField(constraints=[SQL("DEFAULT '0'::bigint")])
    state = TextField(constraints=[SQL("DEFAULT 'initiated'::text")])
    updated_at = DateTimeField(
        constraints=[SQL("DEFAULT (now() AT TIME ZONE 'utc'::text)")]
    )
    workflow_name = TextField(null=True)

    class Meta:
        schema = "public"
        table_name = "task"


class BasePromptLog(BaseDatabaseModel):
    completion_tokens = BigIntegerField(constraints=[SQL("DEFAULT '0'::bigint")])
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = BigAutoField()
    model = TextField()
    prompt = TextField()
    prompt_hash = TextField()
    prompt_tokens = BigIntegerField(constraints=[SQL("DEFAULT '0'::bigint")])
    request_time_ms = BigIntegerField()
    result = TextField()
    task = ForeignKeyField(column_name="task_id", field="id", model=BaseTask, null=True)

    class Meta:
        schema = "public"
        table_name = "prompt_log"
        indexes = ((("prompt_hash", "model"), True),)


class BaseUserAccount(BaseDatabaseModel):
    account_id = UUIDField()
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = BigAutoField()
    user_id = UUIDField(constraints=[SQL("DEFAULT auth.uid()")])

    class Meta:
        schema = "public"
        table_name = "user_account"
        indexes = ((("user_id", "account_id"), True),)
