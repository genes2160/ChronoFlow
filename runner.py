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


def main(target_date: str | None = None):
    log("scan", "Starting ChronoFlow pipeline")

    tracker = load_tracker()

    files = scan_files()
    normalized = normalize(files)

    if target_date and target_date != "__all__":
        before_count = len(normalized)
        normalized = [
            f for f in normalized
            if f.get("date") and f["date"].strftime("%Y-%m-%d") == target_date
        ]
        log(
            "filter",
            f"Scoped organize by date={target_date} "
            f"→ kept {len(normalized)} of {before_count} files"
        )
    else:
        log("filter", "Organize scope = all dates")

    organized = organize(normalized)

    statuses = process_json_files(organized, tracker)

    save_tracker(tracker)

    log(
        "success",
        f"Scanned {len(files)} raw files, organized {len(organized)}, Pipeline complete; {statuses}"
    )

    return statuses


if __name__ == "__main__":
    main()