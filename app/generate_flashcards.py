import datetime
import re
from typing import List

from datashare import PersonDataEntry
from flashcards_template import get_flashcard_template
from openai_utils import gpt_response_to_json

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
def generate_page(project_name, email_datetime, person_data_entries: List[PersonDataEntry], page_template=None):
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
            message_type = draft.get("message_type")
            if message_type.startswith("to "):
                message_type = message_type[3:]

            todo_element_id = f"{element_id}-todo{j}"
            outreach_draft = draft.get("outreach_draft", "NO DRAFT GENERATED").strip('"')
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

    email_dt_str = email_datetime.strftime('%B %d, %H:%M')
    template_vars = {
        "title": f"{project_name} - {email_dt_str}",
        "project_name": project_name,  # ideally the event name
        "sub_project_name": email_dt_str,
        SUB_TEMPLATE_KEY: {
            "person_head": person_heads,
            "person_body": person_bodies,
        }
    }

    return fill_template(page_template, template_vars)


# ======== IGNORE BELOW - ONLY FOR LOCAL TESTING PURPOSES ==============
# TODO(P2): Make these files (or get these from DynamoDB)
test_summaries = """[{"name": "Wojciech Kretowski", "role": "Poland", "industry": null, "vibes": "I had a great first impression of them", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Learn more about their startup Dekognity", "Potentially connect them with investors or mentors"], "transcript": ["he introduced me to two Polish founders", "that do a startup called Dekognity.", "The name of the founders is Wojciech Kretowski", "and Katarzyna Stankiewicz."], "error": null}, {"name": "Katarzyna Stankiewicz", "role": "Poland", "industry": null, "vibes": "I met them through a friend who introduced me to them. They seemed very enthusiastic about their startup and were eager to share their ideas with me.", "priority": 4, "needs": null, "contact_info": "I got their contact information and we are connected on LinkedIn.", "follow_ups": ["Schedule a follow-up call to learn more about their startup idea and offer any help I can provide."], "transcript": ["he introduced me to two Polish founders", "that do a startup called Dekognity.", "The name of the founders is Wojciech Kretowski", "and Katarzyna Stankiewicz.", "Katarzyna is just graduating from Imperial in data science.", "And basically the startup is basically teaching people,"], "error": null}, {"name": "Miguel Coelho", "role": "Dubai", "industry": "B2B SaaS", "vibes": "interesting", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Add Miguel to my network"], "transcript": ["Then I also talked to Miguel Coelho who did a work on MBA and he's he worked at Salesforce and SAP before. And he has a B2B SaaS startup, which might be interesting for us, but he is probably he's based in Dubai and he has a startup here.", "So it's probably not relevant when it comes to geography. But I would just like to have him in my network, basically."], "error": null}, {"name": "Daria Derkach", "role": null, "industry": "Productivity tools and Future of work", "vibes": "Positive, impressed that she is a mentor at First Round and Berkeley Skydeck", "priority": 4, "needs": null, "contact_info": null, "follow_ups": ["Research more about Atlassian and its products", "Reach out to Daria to schedule a follow-up call"], "transcript": ["Give me a second, with a woman who just became a mentor. Her name is Daria Derkach and she's engineering manager at Atlassian. She's mentor at First Round and Berkeley Skydeck.", "What I would like to know more about her is basically what is sort of her sector focus and also what she could basically give a second opinion on when we ever need that. Also when it comes to Atlassian, obviously it's sort of like a productivity tool, right? And like future of work tool. So I would definitely sort of have her sort of in my mind when there is anything when it comes to productivity tools and future of work."], "error": null}, {"name": "Valentina", "role": "Vibranium VC", "industry": null, "vibes": "I've met her a few times and my general impression is positive", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["She invited me, so I should follow up with her to see if she has any opportunities"], "transcript": ["the first person I talked with, Valentina from Vibranium VC", "I met her a few times and she invited me"], "error": null}, {"name": "Alexander", "role": null, "industry": "Cleantech", "vibes": "Didn't really get to know him that well", "priority": 3, "needs": null, "contact_info": null, "follow_ups": ["Try to connect with him on LinkedIn to learn more about his work in Cleantech"], "transcript": ["there was a guy called Alexander", "I had a conversation with, but he is in Cleantech", "we didn't really talk that much", "I don't know what is the name of the startup", "I don't know his full name either"], "error": null}, {"name": "Abishek Chopra", "role": null, "industry": "quantum computing", "vibes": "I didn't talk to him much, so I can't say much about his vibes.", "priority": 3, "needs": null, "contact_info": null, "follow_ups": null, "transcript": ["there was a guy called Abishek Chopra.", "And he is in quantum computing"], "error": null}]"""
test_todolist = """[{"name": "Wojciech Kretowski", "message_type": "to learn more about their company", "outreach_draft": "Hi Wojciech! It was great meeting you last night at the networking event. I was really impressed by the two Polish founders you introduced me to that are working on Dekognity. I'd love to learn more about their startup and your experiences working with them. Let's connect soon!"}, {"name": "Wojciech Kretowski", "message_type": "to Learn more about their startup Dekognity", "outreach_draft": "Hi Wojciech! It was great meeting you at the networking event last night and learning about your startup Dekognity. I'd love to hear more about your vision for the company and how it's been going so far. Maybe we could grab coffee sometime this week and chat further?"}, {"name": "Wojciech Kretowski", "message_type": "to Potentially connect them with investors or mentors", "outreach_draft": "Hey Wojciech! It was great meeting you at the networking event last night. I had a great first impression of you and wanted to connect you with some investors or mentors in your industry. You mentioned you're involved in a startup called Dekognity with Katarzyna Stankiewicz, correct? Let me know if there's anything I can do to help support your venture!"}, {"name": "Katarzyna Stankiewicz", "message_type": "to learn more about their company", "outreach_draft": "Hey Katarzyna! It was great meeting you at the networking event last night. I was really intrigued by your startup and the ideas you shared with me. Can you tell me more about Dekognity and the work you are doing?"}, {"name": "Katarzyna Stankiewicz", "message_type": "to Schedule a follow-up call to learn more about their startup idea and offer any help I can provide.", "outreach_draft": "Hey Katarzyna, it was great meeting you at the networking event last night! Your enthusiasm for your startup Dekognity was contagious, and I'd love to learn more about it. I'm available for a quick call this week if that works for you. Let me know!"}, {"name": "Miguel Coelho", "message_type": "to learn more about their company", "outreach_draft": "\"Hey Miguel! It was great meeting you last night and chatting about your experience in B2B SaaS. As someone who is also in the industry, I would love to learn more about your startup and how it's making an impact. Let's connect and schedule a call when you have a chance!\""}, {"name": "Miguel Coelho", "message_type": "to Add Miguel to my network", "outreach_draft": "Hey Miguel,It was great meeting you at the networking event yesterday! Your background with Salesforce and SAP, and the fact that you have a B2B SaaS startup based in Dubai, really caught my attention. I would love to connect with you and keep in touch. Best regards,[Your Name]"}, {"name": "Daria Derkach", "message_type": "to learn more about their company", "outreach_draft": "\"Hi Daria, it was great meeting you at the networking event yesterday. I was really impressed to hear that you're a mentor at First Round and Berkeley Skydeck. I would love to hear more about what led you to become a mentor and also learn more about your company's focus on productivity tools and the future of work. Would you be available for a quick chat sometime this week?\""}, {"name": "Daria Derkach", "message_type": "to Research more about Atlassian and its products", "outreach_draft": "Hi Daria, it was great meeting you at the networking event last night. I was impressed to hear that you are a mentor at First Round and Berkeley Skydeck. I also noticed that you are an engineering manager at Atlassian. I'm interested in learning more about Atlassian and its products, specifically in the productivity tools and future of work sector. Would love to chat more if you have a free moment."}, {"name": "Daria Derkach", "message_type": "to Reach out to Daria to schedule a follow-up call", "outreach_draft": "Hi Daria, it was great meeting you last night at the networking event! Your experience as a mentor at First Round and Berkeley Skydeck impressed me, and I would love to learn more about your expertise in productivity tools and the future of work. Would you be available for a follow-up call to discuss further? Thank you!"}, {"name": "Valentina", "message_type": "to learn more about their company", "outreach_draft": "\"Hey Valentina! It was great seeing you again at the networking event last night. I'm interested in learning more about Vibranium VC and what you guys are up to these days. Would love to chat if you have some time. Best, [Your Name]\""}, {"name": "Valentina", "message_type": "to She invited me, so I should follow up with her to see if she has any opportunities", "outreach_draft": "Hi Valentina, it was great meeting you at the networking event last night. I've met you a few times and have always had a positive impression. Thank you again for inviting me. I wanted to follow up and see if there are any opportunities for us to collaborate or if there's anything I can do to assist you. Best regards."}, {"name": "Alexander", "message_type": "to learn more about their company", "outreach_draft": "Hey Alexander! It was great meeting you last night at the networking event. I remember you mentioning that you're in the Cleantech industry, which is really interesting to me. I'd love to learn more about your company and what you're working on. Would you be available to chat sometime this week?"}, {"name": "Alexander", "message_type": "to Try to connect with him on LinkedIn to learn more about his work in Cleantech", "outreach_draft": "Hey Alexander, it was great meeting you at the networking event last night! I really enjoyed our brief conversation about Cleantech, and I would love to connect with you on LinkedIn to learn more about your work in the industry. Hope to talk with you soon!"}, {"name": "Abishek Chopra", "message_type": "to learn more about their company", "outreach_draft": "\"Hey Abishek, it was great meeting you at the networking event last night. I was impressed to hear about your work in the exciting field of quantum computing. Can you tell me more about your company and the projects you're currently working on?\""}, {"name": "Abishek Chopra", "message_type": "to thank you, say good to meet you", "outreach_draft": "Hey Abishek, It was great meeting you last night at the networking event. I'm glad we had the chance to chat briefly about your work in quantum computing. Thank you for sharing your insights."}]"""
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
    page1 = generate_page(
        project_name="Katka Sabo",
        email_datetime=datetime.datetime.now(),
        summaries=gpt_response_to_json(test_summaries),
        drafts=gpt_response_to_json(test_todolist),
        page_template=local_test_template,
    )
    page2 = fill_template(local_test_template, test_template_vars, )
    print(f"writing generated page of length {len(page1)}")
    with open("assets/index.html", "w") as handle:
        handle.write(page1)
