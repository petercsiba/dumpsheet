import datetime
import json
import time
from typing import Any

import pytz


class Timer:
    def __init__(self, label):
        self.label = label

    def __enter__(self):
        self.start_time = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_time = time.time() - self.start_time
        print("{}: {:.2f} seconds".format(self.label, elapsed_time))


def safe_none_or_empty(x) -> bool:
    if x is None:
        return True
    if isinstance(x, list):
        return len(x) == 0
    if isinstance(x, dict):
        return len(x) == 0
    if isinstance(x, str):
        return x == "unknown" or len(x) == 0
    return len(str(x)) == 0


def _is_json_serializable(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, ValueError):
        return False


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


def get_local_timezone() -> pytz.tzinfo:
    return datetime.datetime.now().astimezone().tzinfo
