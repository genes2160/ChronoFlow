import re
from datetime import datetime

def extract_date(filename: str):
    iso = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}", filename)
    if iso:
        return datetime.fromisoformat(iso.group())

    ts = re.search(r"\d{10,13}", filename)
    if ts:
        val = int(ts.group())
        if len(ts.group()) == 13:
            val = val / 1000
        return datetime.fromtimestamp(val)

    return None


def detect_type(path):
    name = path.name.lower()

    if name.endswith(".json"):
        return "transcript"

    if name.endswith(".webm"):
        if "audio" in name:
            return "audio"
        if "video" in name:
            return "video"
        return "media"

    return "unknown"