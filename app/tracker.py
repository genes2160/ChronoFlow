import json
from config import TRACK_FILE

def load_tracker():
    if not TRACK_FILE.exists():
        return {}

    try:
        with open(TRACK_FILE) as f:
            content = f.read().strip()

            if not content:
                return {}

            return json.loads(content)

    except json.JSONDecodeError:
        print("⚠️ Tracker file corrupted. Resetting...")
        return {}


def save_tracker(data):
    with open(TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_processed(tracker, filename):
    return filename in tracker


def mark_processed(tracker, filename):
    tracker[filename] = True