import datetime
import json
from typing import Any


def _is_json_serializable(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


# Convert common types
def _datetime_converter(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _datetime_converter(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_datetime_converter(element) for element in obj]
    else:
        return obj


def to_json_serializable(d: dict) -> Any:
    d = _datetime_converter(d)
    if not _is_json_serializable(d):
        print(
            f"ERROR: generated output ain't json serializable (type {type(d)}), converting to str"
        )
        d = str(d)
    return d
