from typing import List

import pytest

from app.contacts_dump import extract_everyone_i_have_talked_to

from common.gpt_client import open_ai_client_with_db_cache
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


def assert_list_equal_with_fuzzy(given: List, expected: List):
    assert len(given) == len(expected), f"length matches for {given} vs {expected}"
    for i, expected_item in enumerate(expected):
        given_item = given[i]
        assert (
            expected_item == FUZZY_PLACEHOLDER or given_item == expected_item
        ), f"item {i}"


who_i_talked_to_test_case_1 = """
Okay, met Penelope. She's doing executive reporting, which is pretty cool.
So, she's pregnant right now. I don't think we can do anything together right now.
But maybe she will be a perfect person to do a copy, but it has to be done like a while later.
She's pregnant in August, so six months after August, maybe meet for coffee.
And then also I will be off well, so I will be able to engage her while I'm pregnant.
Another guy I met is Ricardo. He has a weird role, vice president relationship manager at X&Y Bank.
I have no idea what he does. He seemed to be really nice. He has also two children.
So, that might be something interesting to discuss. Another person I met, I don't remember his name.
And he was doing something with real estate, but he didn't ask my contact, so I didn't ask his either.
Seems to be doing something with real estate investments. Probably can find him on LinkedIn.
He's 2014 class, I want to say. I think something like that. We'll see.
"""
who_i_talked_to_test_case_2 = """
Okay, I just talked to Katka, Katka Sabo.
She gave me good advice on how to do the marketing, how to generate leads.
She recommended me to go to the Amy Porterfield's website and check out her free content, especially the webinars.
She says she's very helpful in the webinars, but I should not buy any content from her because she still has access,
Katka still has access to that, so we could use that. And also she said Gong has great lead magnets,
so this is a good input on how to rebuild our website. To have, not to have just like a sign up for a waitlist,
but do the lead magnets there. And we are, yeah, and Katka sent me some funny stories she wrote,
so I should keep her updated on my trip to my equivalent of Bangladesh, and we're going to walk on Friday,
the usual 8am time, so I'm excited to that. So write a quick follow-up to Katka that we had a great time,
and about the next steps, and then keep it under 500 characters.
"""


def test_people_name_extraction():
    gpt_client = open_ai_client_with_db_cache()
    test_cases = {
        "with anonymous and month August": {
            "input": who_i_talked_to_test_case_1,
            "output": ["Penelope", "Ricardo", FUZZY_PLACEHOLDER],
        },
        "with mentioning public person and and company": {
            "input": who_i_talked_to_test_case_2,
            "output": ["Katka Sabo"],
        },
        "empty transcript": {
            "input": ".",  # Yielded ["Janet", "John", "new member of the sales team", "Sarah from HR"]
            "output": [],
        },
    }
    for name, test_case in test_cases.items():
        print(f"test_case: {name}")
        given = extract_everyone_i_have_talked_to(
            gpt_client, full_transcript=test_case["input"]
        )
        expected = test_case["output"]
        assert_list_equal_with_fuzzy(given, expected)
