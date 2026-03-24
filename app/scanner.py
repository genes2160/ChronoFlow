from config import RAW_DIR
from app.utils import log

def scan_files():
    files = [f for f in RAW_DIR.iterdir() if f.is_file()]

    log("scan", f"Scanning raw folder...")
    log("found", f"{len(files)} files detected")

    return files