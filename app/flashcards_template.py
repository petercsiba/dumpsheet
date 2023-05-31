import os


# TODO: Try to improve in https://www.framer.com
def get_flashcard_template():
    possible_subdirs = ["", "app/", "assets/", "../assets/"]
    template_filename = "index.html.template"
    for subdir in possible_subdirs:
        filepath = f"{subdir}{template_filename}"
        if os.path.exists(filepath):
            with open(filepath, "r") as handle:
                return handle.read()
    print(f"ERROR: Could NOT locate {template_filename} in {possible_subdirs}")