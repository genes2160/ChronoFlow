from app.scanner import scan_files
from app.parser import extract_date, detect_type
from app.organizer import organize
from app.processor import process_json_files
from app.tracker import load_tracker, save_tracker
from app.utils import log


def normalize(files):
    output = []

    for f in files:
        file_type = detect_type(f)
        date = extract_date(f.name)

        if not date:
            log("warn", f"No date found → {f.name}")
        else:
            log("process", f"{f.name} → {file_type} | {date.date()}")

        output.append({
            "path": f,
            "type": file_type,
            "date": date
        })

    return output


def main():
    log("scan", "Starting ChronoFlow pipeline")

    tracker = load_tracker()

    files = scan_files()

    normalized = normalize(files)

    organized = organize(normalized)

    process_json_files(organized, tracker)

    save_tracker(tracker)

    log("success", "Pipeline complete")


if __name__ == "__main__":
    main()