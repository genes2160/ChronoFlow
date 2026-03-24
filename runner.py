from app.scanner import scan_files
from app.parser import extract_date, detect_type
from app.organizer import organize
from app.processor import process_json_files
from app.tracker import load_tracker, save_tracker


def normalize(files):
    output = []

    for f in files:
        output.append({
            "path": f,
            "type": detect_type(f),
            "date": extract_date(f.name)
        })

    return output


def main():
    tracker = load_tracker()

    files = scan_files()

    normalized = normalize(files)

    organized = organize(normalized)

    process_json_files(organized, tracker)

    save_tracker(tracker)


if __name__ == "__main__":
    main()