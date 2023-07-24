from peewee import *
from playhouse.postgres_ext import *

# NOTE: this file is fully generated, if you change something, it will go away
from database.client import database_proxy


class UnknownField(object):
    def __init__(self, *_, **__):
        pass


class BaseModel(Model):
    class Meta:
        database = database_proxy


class BaseOnboarding(BaseModel):
    email = TextField(null=True, unique=True)
    id = BigAutoField()
    ip_address = TextField(null=True)
    referer = TextField(null=True)
    utm_source = TextField(null=True)

    class Meta:
        schema = "public"
        table_name = "onboarding"


class BaseUsers(BaseModel):
    aud = CharField(null=True)
    confirmation_sent_at = DateTimeField(null=True)
    confirmation_token = CharField(null=True)
    confirmed_at = DateTimeField(null=True)
    created_at = DateTimeField(null=True)
    email = CharField(null=True)
    email_change = CharField(null=True)
    email_change_sent_at = DateTimeField(null=True)
    email_change_token = CharField(null=True)
    encrypted_password = CharField(null=True)
    id = UUIDField(null=True)
    instance_id = UUIDField(null=True)
    invited_at = DateTimeField(null=True)
    is_super_admin = BooleanField(null=True)
    last_sign_in_at = DateTimeField(null=True)
    raw_app_meta_data = BinaryJSONField(null=True)
    raw_user_meta_data = BinaryJSONField(null=True)
    recovery_sent_at = DateTimeField(null=True)
    recovery_token = CharField(null=True)
    role = CharField(null=True)
    updated_at = DateTimeField(null=True)

    class Meta:
        schema = "auth"
        table_name = "users"
        primary_key = False


class BaseAccount(BaseModel):
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    full_name = TextField(null=True)
    id = UUIDField(constraints=[SQL("DEFAULT gen_random_uuid()")], primary_key=True)
    onboarding = ForeignKeyField(
        column_name="onboarding_id", field="id", model=BaseOnboarding, unique=True
    )
    user = ForeignKeyField(
        column_name="user_id", field="id", model=BaseUsers, null=True
    )

    class Meta:
        schema = "public"
        table_name = "account"


class BaseDataEntry(BaseModel):
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


class BaseEmailLog(BaseModel):
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


class BasePromptLog(BaseModel):
    completion_tokens = BigIntegerField(constraints=[SQL("DEFAULT '0'::bigint")])
    created_at = DateTimeField(constraints=[SQL("DEFAULT now()")])
    id = BigAutoField()
    model = TextField()
    prompt = TextField()
    prompt_hash = TextField()
    prompt_tokens = BigIntegerField(constraints=[SQL("DEFAULT '0'::bigint")])
    request_time_ms = BigIntegerField()
    result = TextField()

    class Meta:
        schema = "public"
        table_name = "prompt_log"
        indexes = ((("prompt_hash", "model"), True),)
