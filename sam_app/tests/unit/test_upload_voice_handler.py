import json
from uuid import UUID

import pytest

from database.account import Account
from database.client import (
    POSTGRES_LOGIN_URL_FROM_ENV,
    connect_to_postgres_i_will_call_disconnect_i_promise,
    disconnect_from_postgres_as_i_promised,
)
from database.models import BaseOnboarding

from ...upload_voice import app


@pytest.fixture(scope="module", autouse=True)
def db_connection():
    db = connect_to_postgres_i_will_call_disconnect_i_promise(
        POSTGRES_LOGIN_URL_FROM_ENV
    )
    print("truncating tables")
    db.execute_sql('TRUNCATE TABLE "data_entry" CASCADE')
    db.execute_sql('TRUNCATE TABLE "onboarding" CASCADE')
    db.execute_sql('TRUNCATE TABLE "account" CASCADE')

    yield

    disconnect_from_postgres_as_i_promised()


@pytest.fixture()
def test_get_upload_voice():
    return {
        "body": "{}",
        "resource": "/upload/voice",
        "requestContext": {
            "httpMethod": "GET",
            "requestId": "c6af9ac6-7b61-11e6-9a41-93e8deadbeef",
            "identity": {
                "sourceIp": "127.0.0.1",
            },
        },
        "headers": {
            "origin": "https://app.voxana.ai",
        },
        "httpMethod": "GET",
        "path": "/upload/voice",
    }


def get_event_for_post_upload_voice(account_id: UUID):
    return {
        "body": json.dumps(
            {"email": "petherz+test1@gmail.com", "account_id": str(account_id)}
        ),
        "resource": "/upload/voice",
        "requestContext": {
            "httpMethod": "POST",
            "requestId": "c6af9ac6-7b61-11e6-9a41-1234deadbeef",
            "identity": {
                "sourceIp": "127.0.0.1",
            },
        },
        "headers": {
            "origin": "https://app.voxana.ai",
        },
        "httpMethod": "POST",
        "path": "/upload/voice",
    }


def test_lambda_handler_get_upload_voice(db_connection, test_get_upload_voice):
    ret = app.lambda_handler(test_get_upload_voice, "")
    assert ret["statusCode"] == 201

    data = json.loads(ret["body"])

    assert "presigned_url" in data
    assert "email" in data
    assert "account_id" in data


def test_lambda_handler_post_upload_voice(db_connection):
    orig_account = Account.get_or_onboard_for_ip("127.0.0.1")

    ret = app.lambda_handler(get_event_for_post_upload_voice(orig_account.id), "")
    assert ret["statusCode"] == 200

    updated_onboarding = BaseOnboarding.get_by_id(orig_account.onboarding)
    expected_email = "petherz+test1@gmail.com"
    assert updated_onboarding.email == expected_email
    # Test some extra functionality on the Account class for more confidence in my sleep
    updated_account = Account.get_by_id(orig_account.id)
    assert updated_account.get_email() == expected_email
    assert Account.get_by_email_or_none(expected_email).id == orig_account.id
    assert Account.get_or_onboard_for_email(expected_email).id == orig_account.id
