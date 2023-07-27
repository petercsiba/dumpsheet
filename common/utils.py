import time


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
