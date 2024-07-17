import pytest

from common.openai_client import gpt_response_to_json
from database.client import (
    POSTGRES_LOGIN_URL_FROM_ENV,
    connect_to_postgres_i_will_call_disconnect_i_promise,
    disconnect_from_postgres_as_i_promised,
)


@pytest.fixture(scope="module", autouse=True)
def db_connection():
    connect_to_postgres_i_will_call_disconnect_i_promise(POSTGRES_LOGIN_URL_FROM_ENV)
    print("truncating tables")

    yield

    disconnect_from_postgres_as_i_promised()


FUZZY_PLACEHOLDER = "__FUZZY__"

# We over-fit the raw_response post-processing so we have to got back to basics
problem_json_1 = """
{
  "Janet": "",
  "John": "",
  "new member of the sales team": "",
  "Sarah from HR": ""
}
"""


def test_gpt_response_to_json():
    test_cases = {
        "empty values": {
            "input": problem_json_1,
            "output": {
                "Janet": "",
                "John": "",
                "new member of the sales team": "",
                "Sarah from HR": "",
            },
        },
    }
    for name, test_case in test_cases.items():
        print(f"test_case: {name}")
        given = gpt_response_to_json(test_case["input"])
        expected = test_case["output"]
        assert given == expected
