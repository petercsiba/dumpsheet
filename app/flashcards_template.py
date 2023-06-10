import os


# TODO(P0, ux): Much improve visuals - best way is to go with Flutter (or React Native)
#   This is a big project MAYBE makes sense to get sth quick in pure-html? So I can keep generating webpage-links.
#   HTML only: https://ui8.net/whiteuistore/products/betacrm-html-templates
#    * There are some quite good iOS things.
#   You can convert react native https://github.com/GeekyAnts/react-native-to-flutter
#   DIY not worth it https://www.framer.com
def get_flashcard_template():
    possible_subdirs = ["", "app/", "assets/", "../assets/"]
    template_filename = "index.html.template"
    for subdir in possible_subdirs:
        filepath = f"{subdir}{template_filename}"
        if os.path.exists(filepath):
            with open(filepath, "r") as handle:
                return handle.read()
    print(f"ERROR: Could NOT locate {template_filename} in {possible_subdirs}")
