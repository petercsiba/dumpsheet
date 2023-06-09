import datetime
import json
import re
from typing import List

from datashare import PersonDataEntry, DataEntry, dict_to_dataclass
from flashcards_template import get_flashcard_template

SUB_TEMPLATE_KEY = "__templates"


def fill_template(template, template_vars, depth=1):
    # First get all repeating sub-templates (this can be recursive)
    if SUB_TEMPLATE_KEY in template_vars:
        for subkey, sub_template_vars_list in template_vars[SUB_TEMPLATE_KEY].items():
            # Find matches using the pattern
            # TODO: Less strict with the whitespace inside of {{ }}
            extract_pattern = r"{{ " + subkey + r"\.begin }}(.*?){{ " + subkey + r"\.end }}"
            matches = re.findall(extract_pattern, template, re.DOTALL)
            if not matches:
                print(f"No match found for expected `{subkey}` - nothing will be replaced.")
                continue

            print(f"Updating template for {subkey} with {template_vars.keys()}")
            replacements = []
            sub_template = matches[0]
            # Same pattern but without the braces (.*) inside
            replace_pattern = r"{{ " + subkey + r"\.begin }}.*{{ " + subkey + r"\.end }}"

            for sub_template_vars in sub_template_vars_list:
                replacements.append(fill_template(sub_template, sub_template_vars, depth=depth+1))

            # Update the original template
            if len(replacements) == 0:
                print(f"NOTE: No sub_template_vars found for {subkey}, replacing with empty")
            replacement = "\n\n".join(replacements)
            template = re.sub(replace_pattern, replacement, template, flags=re.DOTALL)

    # Second fill in the rest
    for var, value in template_vars.items():
        # Already done
        if var == SUB_TEMPLATE_KEY:
            continue

        value = "Unknown" if value is None else str(value)
        # print(f"replacing {var} with {value}")
        template = re.sub(r"{{ " + var + " }}", value, template, flags=re.DOTALL)

    if depth == 1:
        pattern = r"{{\s*(\w+)\s*}}"
        matches = re.findall(pattern, template)
        if matches:
            print(f"WARNING: Some non-replaced template variables left {matches}")

    return template


# Whole function is about translating the input JSON objects into my custom
# fill_template templating framework (really just a function).
def generate_page(project_name, event_timestamp, person_data_entries: List[PersonDataEntry], page_template=None):
    print(f"Running generate webpage")
    if page_template is None:
        page_template = get_flashcard_template()

    person_heads = []
    person_bodies = []
    for i, person in enumerate(person_data_entries):
        element_id = f"person{i}"
        name = person.name
        style_display = "gpt-active-button" if i == 0 else ""
        head = {
            "person_head.element_id": element_id,
            "person_head.style_display": style_display,
            "person_head.name": name,
        }
        person_heads.append(head)

        follow_ups = []
        for j, draft in enumerate(person.drafts):
            message_type = draft.intent
            todo_element_id = f"{element_id}-todo{j}"
            outreach_draft = (draft.message or "NO DRAFT GENERATED").strip('"')
            follow_up = {
                "follow_ups.element_id": todo_element_id,
                "follow_ups.feedback_element_id": f"feedback-{todo_element_id}",
                "follow_ups.option_num": j+1,
                "follow_ups.message_type": message_type,
                "follow_ups.outreach_draft": outreach_draft,
            }
            follow_ups.append(follow_up)

        transcript = person.transcript
        if isinstance(transcript, list):
            transcript = "<br />".join(transcript)
        style_display = "block" if i == 0 else "none"
        body = {
            SUB_TEMPLATE_KEY: {
                "follow_ups": follow_ups
            },
            # TODO(P0, vertical-saas): The summary list should be generated here.
            "person_body.element_id": element_id,
            "person_body.style_display": style_display,
            "person_body.name": name,
            "person_body.mnemonic": person.mnemonic,
            "person_body.mnemonic_explanation": person.mnemonic_explanation,
            "person_body.priority": person.priority,
            "person_body.industry": person.industry,
            "person_body.vibes": person.vibes,
            "person_body.role": person.role,
            # "person_body.contact_info": person.contact_info,
            "person_body.transcript": transcript,
            "person_body.parsing_error": f"ParsingError: {person.parsing_error}" if person.parsing_error else "",
        }
        person_bodies.append(body)

    event_dt_str = event_timestamp.strftime('%B %d, %H:%M')
    template_vars = {
        "title": f"{project_name} - {event_dt_str}",
        "project_name": project_name,  # ideally the event name
        "sub_project_name": event_dt_str,
        SUB_TEMPLATE_KEY: {
            "person_head": person_heads,
            "person_body": person_bodies,
        }
    }

    return fill_template(page_template, template_vars)


# ======== IGNORE BELOW - ONLY FOR LOCAL TESTING PURPOSES ==============
# TODO(P2): Make these files (or get these from DynamoDB)
test_data_entries_raw = """[{"name": "un-named man 1", "transcript": ["the guy, I don't remember his name, but he was doing car reselling", "they had some big deal, Bugatti, yay", "he worked in One Market Street two months ago before he quit his job"], "mnemonic": "CR", "mnemonic_explanation": "Mnemonic for Car Reseller", "vibes": "Excited and impressed by his big deal with Bugatti", "role": "Entrepreneur", "industry": "Automotive", "priority": "P1 - High: This is important & needed", "follow_ups": null, "needs": ["None mentioned"], "additional_metadata": {}, "drafts": [], "parsing_error": null}, {"name": "un-named man 2", "transcript": ["the guy is from SoCal, but he has worked in B2B SaaS for his whole life", "he went to New York to Techstars", "This guy, reach out to him on LinkedIn", "He is part of a current cohort and he can do introductions and he offered to do an Antler introduction to me"], "mnemonic": "SaaS Cali", "mnemonic_explanation": "A two word mnemonic that combines his expertise in B2B SaaS and his origin in Southern California", "vibes": "Positive vibes, seemed friendly and approachable", "role": "Current member of a Techstars cohort", "industry": "B2B SaaS", "priority": "P1 - High: This is important & needed", "follow_ups": ["Connect on LinkedIn", "Ask for intros to his network", "Follow up on Antler introduction"], "needs": ["None mentioned"], "additional_metadata": {}, "drafts": [], "parsing_error": null}, {"name": "Valentina", "transcript": "I really need to reach out to her and tell her that I really like her. The partnership is really good. I really like her. I really like her. The partner who was from Vibranium.", "mnemonic": "Vi Partner", "mnemonic_explanation": "Short for 'Vibranium Partner'", "vibes": "Positive and enthusiastic", "role": "Partner", "industry": "Unknown", "priority": "P1 - High: This is important & needed", "follow_ups": ["Reach out and express liking for her", "Discuss potential partnership opportunities further"], "needs": [], "additional_metadata": {}, "drafts": [], "parsing_error": null}, {"name": "Catalina", "transcript": ["There is a girl, Catalina, she's from Romania"], "mnemonic": "Cat Ro", "mnemonic_explanation": "Her name reminds me of a cat and she's from Romania", "vibes": "I only just met her, but she seems friendly and approachable.", "role": null, "industry": null, "priority": "P2 - Medium: Nice to have", "follow_ups": null, "needs": null, "additional_metadata": {}, "drafts": [], "parsing_error": null}, {"name": "Gabriel", "transcript": ["the third guy, Gabriel", "his company got acquired by Carta and he is now helping Carta and their his previous, his original company in their partnerships"], "mnemonic": "Carta Gabriel", "mnemonic_explanation": "He was previously associated with Carta and now helps them with partnerships", "vibes": "Seems knowledgeable and driven", "role": "Previously owned a company that got acquired by Carta, currently helping Carta", "industry": "Partnerships", "priority": "P2 - Medium: Nice to have", "follow_ups": null, "needs": ["Understanding more about his experience with Carta and insights on partnerships"], "additional_metadata": {}, "drafts": [], "parsing_error": null}, {"name": "un-named moderator", "transcript": ["there was one moderator and four people on the panel", "I have texts about all of them"], "mnemonic": null, "mnemonic_explanation": null, "vibes": null, "role": null, "industry": null, "priority": "P4 - Low: Just don't bother", "follow_ups": [], "needs": [], "additional_metadata": {}, "drafts": [], "parsing_error": "Sorry, I cannot complete this prompt as the given transcript does not contain information about me meeting a person."}]"""
test_template_vars = {
    "title": "My Test Page",
    "project_name": "My Test Page",  # ideally the networking event name
    "website_url": "#",
    SUB_TEMPLATE_KEY: {
        "person_head": [{
            "person_head.element_id": "person1",
            "person_head.name": "Test Person 1",
        }, {
            "person_head.element_id": "person2",
            "person_head.name": "Test Person 2",
        }],
        "person_body": [{
            SUB_TEMPLATE_KEY: {
                "follow_ups": [{
                    "follow_ups.element_id": "person1-todo1",
                    "follow_ups.message_type": "Follow up 1",
                    "follow_ups.outreach_draft": "Dear Person 1",
                }, {
                    "follow_ups.element_id": "person1-todo2",
                    "follow_ups.message_type": "Follow up 2",
                    "follow_ups.outreach_draft": "Dear Person 2",
                }]
            },
            "person_body.element_id": "person1",
            "person_body.name": "Test Person 1",
            "person_body.priority": "High",
            "person_body.industry": "Tech",
            "person_body.vibes": "Chill",
            "person_body.role": "Software Engineer",
            "person_body.contact_info": "AWS",
            "person_body.transcript": "some very long text",
        }, {
            SUB_TEMPLATE_KEY: {
                "follow_ups": [{
                    "follow_ups.message_type": "Some funny quote",
                    "follow_ups.outreach_draft": "Facon",
                }, {
                    "follow_ups.message_type": "Not so funne",
                    "follow_ups.outreach_draft": "afsgs",
                }]
            },
            "person_body.element_id": "person2",
            "person_body.name": "Test Person 2",
            "person_body.priority": "Low",
            "person_body.industry": "Unknown",
            "person_body.vibes": "Inappropriate",
            "person_body.role": "Comedian",
            "person_body.contact_info": "AWS",
            "person_body.transcript": "some very long text again",
        }],
    }
}


if __name__ == "__main__":
    with open("assets/index.html.template", "r") as handle:
        local_test_template = handle.read()

    list_of_dicts = json.loads(test_data_entries_raw)
    data_entries = [dict_to_dataclass(dict_, data_class_type=DataEntry) for dict_ in list_of_dicts]
    pdes = [pde for pde in [de.output_people_entries for de in data_entries]]
    page1 = generate_page(
        project_name="Katka Sabo",
        event_timestamp=datetime.datetime.now(),
        person_data_entries=pdes,
        page_template=local_test_template,
    )
    page2 = fill_template(local_test_template, test_template_vars, )
    print(f"writing generated page of length {len(page1)}")
    with open("assets/index.html", "w") as handle:
        handle.write(page1)
