import json

import pytest

from ...upload_voice import app


@pytest.fixture()
def test_get_upload_voice():
    """Generates API GW Event"""

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


def test_lambda_handler(test_get_upload_voice):
    ret = app.lambda_handler(test_get_upload_voice, "")
    assert ret["statusCode"] == 200

    data = json.loads(ret["body"])

    assert "presigned_url" in data
    assert "is_new_account" in data
    assert "account_id" in data
