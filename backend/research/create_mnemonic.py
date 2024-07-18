from app.datashare import PersonDataEntry
from common.openai_client import OpenAiClient


# TODO: Remove if not needed OR update to new infra - parking it here until then.
def create_mnemonic(gpt_client: OpenAiClient, person: PersonDataEntry):
    # Unfortunately, GPT 3.5 is not as good with creative work resulting into structured output
    # So making a separate query for the mnemonic
    query_mnemonic = (
        "I need your help with a fun little task. "
        f"Can you come up with a catchy three-word phrase that's easy to remember and includes {person.name}? "
        "Here's the catch: all the words should start with the same letter and describe the person."
        "Please output the result on two lines as:\n"
        "* phrase\n"
        "* explanation of it in max 25 words\n"
        f"My notes: {person.get_transcript_text()}"
    )
    raw_mnemonic = gpt_client.run_prompt(query_mnemonic, print_prompt=True)
    non_whitespace_lines = []
    if bool(raw_mnemonic):
        lines = str(raw_mnemonic).split("\n")
        non_whitespace_lines = [line for line in lines if line.strip() != ""]
        if len(non_whitespace_lines) > 0:
            person.mnemonic = non_whitespace_lines[0]
        if len(non_whitespace_lines) > 1:
            person.mnemonic_explanation = non_whitespace_lines[1]
    if len(non_whitespace_lines) < 2:
        print(
            f"WARNING: Could NOT get mnemonic (catch phrase) for {person.name} got raw: {raw_mnemonic}"
        )
