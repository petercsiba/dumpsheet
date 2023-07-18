from peewee import *

database = PostgresqlDatabase('postgres', **{'host': 'localhost', 'port': 54322, 'user': 'postgres'})

class UnknownField(object):
    def __init__(self, *_, **__): pass

class BaseModel(Model):
    class Meta:
        database = database

class PromptLog(BaseModel):
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
        table_name = 'prompt_log'
        indexes = (
            (('prompt_hash', 'model'), True),
        )

