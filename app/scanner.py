from config import RAW_DIR

def scan_files():
    return [f for f in RAW_DIR.iterdir() if f.is_file()]