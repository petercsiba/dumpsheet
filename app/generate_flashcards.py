import re

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

        print(f"replacing {var} with {value}")
        template = re.sub(r"{{ " + var + " }}", value, template, flags=re.DOTALL)

    if depth == 1:
        pattern = r"{{\s*(\w+)\s*}}"
        matches = re.findall(pattern, template)
        if matches:
            print(f"WARNING: Some non-replaced template variables left {matches}")

    return template


def generate_page(template_path, page_title, summaries=None, todo_list=None):
    with open(template_path, "r") as handle:
        template = handle.read()

    template_vars = {
        "title": page_title,
        "project_name": page_title,  # ideally the networking event name
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
                        "follow_ups.message_type": "Follow up 1",
                        "follow_ups.outreach_draft": "Dear Person 1",
                    }, {
                        "follow_ups.message_type": "Follow up 2",
                        "follow_ups.outreach_draft": "Dear Person 2",
                    }]
                },
                "person_body.element_id": "person1",
                "person_body.name": "Test Person 1",
                "person_body.priority": "High",
                "person_body.industry": "Tech",
                "person_body.vibes": "Chill",
                "person_body.from": "San Fran",
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
                "person_body.from": "San Fran",
                "person_body.contact_info": "AWS",
                "person_body.transcript": "some very long text again",
            }],
        }
    }

    return fill_template(template, template_vars)


if __name__ == "__main__":
    page = generate_page("assets/index.html.template", "My Test Page")
    print(f"writing generated page of length {len(page)}")
    with open("assets/index.html", "w") as handle:
        handle.write(page)
