def _deep_merge(dict1: dict, dict2: dict):
    for key in dict2:
        if key in dict1:
            if isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                _deep_merge(dict1[key], dict2[key])
            else:
                dict1[key] = dict2[key]
        else:
            dict1[key] = dict2[key]
    return dict1


BASE_CELL_FORMAT = {
    # backgroundColorStyle takes precedence over backgroundColor, and it allows to specify more using ColorStyle object.
    "backgroundColor": {"blue": 1, "green": 1, "red": 1},
    "backgroundColorStyle": {"rgbColor": {"blue": 1, "green": 1, "red": 1}},
    "borders": {"style": "SOLID", "width": 1},
    # "borders": {"color": {"blue": 0.7176471, "green": 0.7176471, "red": 0.7176471}, "style": "SOLID", "width": 1},
    "padding": {"bottom": 2, "left": 3, "right": 3, "top": 2},
    "textFormat": {
        "bold": False,
        "fontFamily": "Comfortaa",
        "fontSize": 9,
        "foregroundColor": {},
        "italic": False,
        "strikethrough": False,
        "underline": False,
    },
    "wrapStrategy": "WRAP",
    "hyperlinkDisplayType": "PLAIN_TEXT",
}

GRAY_BORDER_FORMAT = {
    "color": {"blue": 0.7176471, "green": 0.7176471, "red": 0.7176471},
    "colorStyle": {
        "rgbColor": {"blue": 0.7176471, "green": 0.7176471, "red": 0.7176471}
    },
    "style": "SOLID",
    "width": 1,
}

GRAY_BORDER_CELL_FORMAT_OVERLAY = {
    "borders": {
        "bottom": GRAY_BORDER_FORMAT,
        "left": GRAY_BORDER_FORMAT,
        "right": GRAY_BORDER_FORMAT,
        "top": GRAY_BORDER_FORMAT,
    }
}

BASE_GRAY_BORDER_CELL_FORMAT = _deep_merge(
    BASE_CELL_FORMAT, GRAY_BORDER_CELL_FORMAT_OVERLAY
)

HEADER_CELL_FORMAT_OVERLAY = {
    "backgroundColor": {"blue": 0.9372549, "green": 0.9372549, "red": 0.9372549},
    "backgroundColorStyle": {
        "rgbColor": {"blue": 0.9372549, "green": 0.9372549, "red": 0.9372549}
    },
    "horizontalAlignment": "LEFT",
    "textFormat": {
        "bold": True,
    },
    "verticalAlignment": "TOP",
}

DATE_CELL_FORMAT_OVERLAY = {
    "numberFormat": {"pattern": 'mmm" "d", "yyyy" at "ham/pm', "type": "DATE_TIME"}
}

BASE_HEADER_CELL_FORMAT = _deep_merge(BASE_CELL_FORMAT, HEADER_CELL_FORMAT_OVERLAY)
HEADER_SMALL_FONT_CELL_FORMAT = _deep_merge(
    BASE_HEADER_CELL_FORMAT, {"textFormat": {"fontSize": 6}}
)
HEADER_DATE_FONT_CELL_FORMAT = _deep_merge(
    BASE_HEADER_CELL_FORMAT, DATE_CELL_FORMAT_OVERLAY
)

TEMPLATES = {
    "base": BASE_CELL_FORMAT,
    "base.gray_border": BASE_GRAY_BORDER_CELL_FORMAT,
    "header": BASE_HEADER_CELL_FORMAT,
    "header.small": HEADER_SMALL_FONT_CELL_FORMAT,
    "header.date": HEADER_DATE_FONT_CELL_FORMAT,
}


# Mostly used to generate our "Google Sheet CSS" classes and see which formats attributes are in use.
def get_overlay_cell_format(new: dict, base: dict = None):
    if base is None:
        base = BASE_CELL_FORMAT

    if "borders" in new:
        if "bottom" in new["borders"]:
            if new["borders"]["bottom"]["color"]["blue"] == 0.7176471:
                print("get_overlay_cell_format switched to gray_border")
                base = BASE_GRAY_BORDER_CELL_FORMAT

    if "backgroundColor" in new:
        if (
            new["backgroundColor"]["blue"]
            == HEADER_CELL_FORMAT_OVERLAY["backgroundColor"]["blue"]
        ):
            print("get_overlay_cell_format switched to header")
            base = BASE_HEADER_CELL_FORMAT

    diff = {}
    for k, v in new.items():
        base_value = base.get(k, {})

        if base_value == v:
            continue  # Skip this attribute if it's the same as in the base

        if isinstance(v, dict):
            _, diff_val = get_overlay_cell_format(v, base_value)
            if diff_val:
                diff[k] = diff_val
        else:
            if base.get(k) != v:
                diff[k] = v
    return base, diff
