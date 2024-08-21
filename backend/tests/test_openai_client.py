import pytest

from gpt_form_filler.openai_client import gpt_response_to_json


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
