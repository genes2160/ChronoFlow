from pathlib import Path
from sqlmodel import select

from app.api.core.db import get_session
from app.api.core.config import settings
from app.api.models.model import Meeting, MediaFile, FileTypeEnum
from app.api.services.migration_service import (
    _extract_meeting_id,
    _detect_file_type,
    _load_json_file,
    migrate_file_record,
    migrate_transcript,
    migrate_captions,
    migrate_captions_and_transcripts,
    migrate_summary,
)
from app.api.schema.schemas import FileType

def fix_missing_files_in_db(target_date: str | None = None) -> dict:
    organized = Path(settings.ORGANIZED_DATA_DIR)

    print("\n🛠 [RECON FIX] Starting missing-file reconciliation")
    print(f"📁 Organized dir: {organized}")
    print(f"🎯 Target date: {target_date or 'ALL'}")

    if not organized.exists():
        print("❌ Organized directory does not exist")
        return {
            "folders_scanned": 0,
            "meetings_checked": 0,
            "files_added": 0,
            "content_migrations_run": 0,
            "items": [],
        }

    date_folders = sorted([f for f in organized.iterdir() if f.is_dir()])
    if target_date:
        date_folders = [f for f in date_folders if f.name == target_date]

    folders_scanned = 0
    meetings_checked = 0
    files_added = 0
    content_migrations_run = 0
    items = []

    with get_session() as session:
        for date_folder in date_folders:
            folders_scanned += 1
            date = date_folder.name
            print(f"\n📆 Processing folder: {date}")

            disk_map: dict[str, list[Path]] = {}

            for f in date_folder.iterdir():
                if not f.is_file():
                    continue

                raw_meeting_id = _extract_meeting_id(f.name)
                if not raw_meeting_id:
                    continue

                dated_meeting_id = f"{raw_meeting_id}-{date}"
                disk_map.setdefault(dated_meeting_id, []).append(f)

            print(f"🧭 Found {len(disk_map)} meeting groups on disk")

            for meeting_id, disk_paths in sorted(disk_map.items()):
                meetings_checked += 1
                print(f"\n🔗 Checking meeting: {meeting_id}")

                meeting = session.exec(
                    select(Meeting).where(Meeting.meeting_id == meeting_id)
                ).first()

                if not meeting:
                    print("   🔴 No DB meeting found -> skipping")
                    items.append({
                        "meeting_id": meeting_id,
                        "date": date,
                        "status": "meeting_missing",
                        "added_files": [],
                        "migrated_content_files": [],
                    })
                    continue

                print(f"   🟢 DB meeting found -> db_pk={meeting.id}")

                db_file_rows = session.exec(
                    select(MediaFile).where(MediaFile.meeting_id == meeting.id)
                ).all()
                db_filenames = set(f.filename for f in db_file_rows)

                added_files = []
                migrated_content_files = []

                for path in sorted(disk_paths, key=lambda p: p.name):
                    filename = path.name
                    print(f"   📄 Disk file: {filename}")

                    if filename in db_filenames:
                        print("      ⏭ already in DB file inventory")
                        continue

                    detected = _detect_file_type(filename)
                    print(f"      🧩 detected_type={detected}")

                    # catalog missing file record
                    if detected == FileType.summary:
                        migrate_file_record(session, meeting, path, FileTypeEnum.summary)
                        added_files.append(filename)

                        raw = _load_json_file(path)
                        if raw:
                            migrate_summary(session, meeting, raw)
                            migrated_content_files.append(filename)
                            content_migrations_run += 1
                            print("      ✅ summary content migrated")

                    elif detected == FileType.captions_and_transcripts:
                        migrate_file_record(session, meeting, path, FileTypeEnum.transcript)
                        added_files.append(filename)

                        raw = _load_json_file(path)
                        if raw:
                            migrate_captions_and_transcripts(session, meeting, raw)
                            migrated_content_files.append(filename)
                            content_migrations_run += 1
                            print("      ✅ captions_and_transcripts content migrated")

                    elif detected == FileType.transcript:
                        migrate_file_record(session, meeting, path, FileTypeEnum.transcript)
                        added_files.append(filename)

                        raw = _load_json_file(path)
                        if raw:
                            migrate_transcript(session, meeting, raw)
                            migrated_content_files.append(filename)
                            content_migrations_run += 1
                            print("      ✅ transcript content migrated")

                    elif detected == FileType.captions:
                        migrate_file_record(session, meeting, path, FileTypeEnum.captions)
                        added_files.append(filename)

                        raw = _load_json_file(path)
                        if raw:
                            migrate_captions(session, meeting, raw)
                            migrated_content_files.append(filename)
                            content_migrations_run += 1
                            print("      ✅ captions content migrated")

                    elif detected == FileType.audio:
                        migrate_file_record(session, meeting, path, FileTypeEnum.audio)
                        added_files.append(filename)
                        print("      ✅ audio file inventory added")

                    elif detected == FileType.video:
                        migrate_file_record(session, meeting, path, FileTypeEnum.video)
                        added_files.append(filename)
                        print("      ✅ video file inventory added")

                    else:
                        print("      ⚠️ unknown type -> skipped")
                        continue

                    files_added += 1
                    db_filenames.add(filename)

                items.append({
                    "meeting_id": meeting_id,
                    "date": date,
                    "status": "fixed" if added_files else "no_change",
                    "added_files": added_files,
                    "migrated_content_files": migrated_content_files,
                })

        session.commit()
        print("\n💾 Reconciliation fix committed")

    print("\n✅ [RECON FIX COMPLETE]")
    print(f"📊 folders_scanned={folders_scanned}")
    print(f"📊 meetings_checked={meetings_checked}")
    print(f"📊 files_added={files_added}")
    print(f"📊 content_migrations_run={content_migrations_run}")

    return {
        "folders_scanned": folders_scanned,
        "meetings_checked": meetings_checked,
        "files_added": files_added,
        "content_migrations_run": content_migrations_run,
        "items": items,
    }
    
   
def reconcile_organized_files_vs_db(target_date: str | None = None) -> dict:
    organized = Path(settings.ORGANIZED_DATA_DIR)

    print("\n🔍 [RECON] Starting reconciliation")
    print(f"📁 Organized dir: {organized}")
    print(f"🎯 Target date: {target_date or 'ALL'}")

    if not organized.exists():
        print("❌ Organized directory does not exist")
        return {
            "folders_scanned": 0,
            "meetings_found_on_disk": 0,
            "meetings_found_in_db": 0,
            "items": [],
        }

    date_folders = sorted([f for f in organized.iterdir() if f.is_dir()])
    print(f"📂 Found {len(date_folders)} total date folders")

    if target_date:
        date_folders = [f for f in date_folders if f.name == target_date]
        print(f"📆 After target_date filter -> {len(date_folders)} folder(s)")

    results = []
    disk_meeting_count = 0
    db_meeting_ids_seen = set()

    with get_session() as session:
        for date_folder in date_folders:
            date = date_folder.name
            print(f"\n📆 Processing folder: {date}")

            disk_map: dict[str, list[str]] = {}

            folder_files = list(date_folder.iterdir())
            print(f"📄 Files found in folder: {len(folder_files)}")

            for f in folder_files:
                if not f.is_file():
                    print(f"   ⏭ Skipping non-file: {f.name}")
                    continue

                print(f"   🔎 Inspecting file: {f.name}")

                raw_meeting_id = _extract_meeting_id(f.name)
                print(f"   🧩 Extracted raw_meeting_id: {raw_meeting_id}")

                if not raw_meeting_id:
                    print(f"   ⚠️ No meeting id extracted -> skipping {f.name}")
                    continue

                dated_meeting_id = f"{raw_meeting_id}-{date}"
                print(f"   🪪 Dated meeting id: {dated_meeting_id}")

                disk_map.setdefault(dated_meeting_id, []).append(f.name)

            print(f"🧭 Built disk_map for {date}: {len(disk_map)} meeting(s)")

            for meeting_id, disk_files in sorted(disk_map.items()):
                print(f"\n🔗 Reconciling meeting: {meeting_id}")
                print(f"   📄 Disk files: {sorted(disk_files)}")

                disk_meeting_count += 1

                meeting = session.exec(
                    select(Meeting).where(Meeting.meeting_id == meeting_id)
                ).first()

                db_files = []
                meeting_db_id = None

                if meeting:
                    meeting_db_id = meeting.id
                    db_meeting_ids_seen.add(meeting.id)
                    print(f"   🟢 DB meeting found -> db_pk={meeting.id}")

                    db_file_rows = session.exec(
                        select(MediaFile).where(MediaFile.meeting_id == meeting.id)
                    ).all()

                    db_files = sorted([f.filename for f in db_file_rows])
                    print(f"   📦 DB files: {db_files}")
                else:
                    print("   🔴 No DB meeting found")

                disk_files_sorted = sorted(disk_files)
                disk_set = set(disk_files_sorted)
                db_set = set(db_files)

                missing_in_db = sorted(list(disk_set - db_set))
                extra_in_db = sorted(list(db_set - disk_set))

                print(f"   ❗ Missing in DB: {missing_in_db}")
                print(f"   ⚠️ Extra in DB: {extra_in_db}")

                results.append({
                    "meeting_id": meeting_id,
                    "date": date,
                    "meeting_db_id": meeting_db_id,
                    "disk_files": disk_files_sorted,
                    "db_files": db_files,
                    "missing_in_db": missing_in_db,
                    "extra_in_db": extra_in_db,
                })

    print("\n✅ [RECON COMPLETE]")
    print(f"📊 folders_scanned={len(date_folders)}")
    print(f"📊 meetings_found_on_disk={disk_meeting_count}")
    print(f"📊 meetings_found_in_db={len(db_meeting_ids_seen)}")

    return {
        "folders_scanned": len(date_folders),
        "meetings_found_on_disk": disk_meeting_count,
        "meetings_found_in_db": len(db_meeting_ids_seen),
        "items": results,
    }
    
    
    