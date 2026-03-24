from pathlib import Path

RAW_DIR = Path("data/raw")
ORG_DIR = Path("data/organized")
LOG_DIR = Path("logs")

TRACK_FILE = LOG_DIR / "processed_files.json"

LOG_DIR.mkdir(exist_ok=True)
ORG_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)