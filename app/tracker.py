import json
from config import TRACK_FILE

def load_tracker():
    if not TRACK_FILE.exists():
        return {}

    with open(TRACK_FILE) as f:
        return json.load(f)


def save_tracker(data):
    with open(TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_processed(tracker, filename):
    return filename in tracker


def mark_processed(tracker, filename):
    tracker[filename] = True