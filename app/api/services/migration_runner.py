# app/api/services/migration_runner.py
"""
ChronoFlow — Backfill runner
Run once:  python -m app.api.services.migration_runner

Prints a verification report at the end.
JSON files stay on disk — delete manually once counts match.
"""

import json
from pathlib import Path
import re
from sqlmodel import Session, select, func

from app.api.core.db import engine
from app.api.core.config import settings
from app.api.models.model import (
    Meeting, Summary, TranscriptTurn,
    Caption, MediaFile, FileTypeEnum
)
from app.api.services.migration_service import migrate_meeting_folder
from app.api.services.meetings_service import _extract_meeting_id, _detect_file_type
from app.api.schema.schemas import FileType
from app.api.services.migration_service import migrate_memory_file, _generate_mem_meeting_id
BATCH_SIZE = 50

_FTYPE_MAP = {
    FileType.audio:   FileTypeEnum.audio,
    FileType.video:   FileTypeEnum.video,
}

# Replace the strict regex with one that accepts both formats
_MEETING_ID_RE = re.compile(
    r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$'          # hrp-axdm-gqm
    r'|^Meet[_–-].+$'                          # Meet_Team_Sync or Meet–NSPSync
    r'|^meet-transcript-.+$'                   # meet-transcript-Meet–...
)
orphan_media: list[Path] = []

def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Could not read {path.name}: {e}")
        return None


# In _count_folder_files — count actual rows inside files, not just files

def _count_folder_files(organized: Path) -> dict:
    counts = {
        "meetings": set(),
        "summaries": 0,
        "transcripts": 0,      # actual turns inside files
        "captions": 0,         # actual caption rows inside files
        "media": 0,
        "memory": 0,
    }

    for date_folder in organized.iterdir():
        if not date_folder.is_dir():
            continue
        for f in date_folder.iterdir():

            # Memory files
            if f.name.startswith("meet-memory") and f.suffix == ".json":
                counts["memory"] += 1
                continue

            ft = _detect_file_type(f.name)
            mid = _extract_meeting_id(f.name)

            if ft == FileType.summary and _MEETING_ID_RE.match(mid):
                counts["summaries"] += 1

            elif ft == FileType.transcript:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    turns = data.get("transcripts", [])
                    counts["transcripts"] += len(
                        [t for t in turns if t.get("text", "").strip()]
                    )
                except Exception:
                    pass

            elif ft == FileType.captions:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    items = data if isinstance(data, list) else (
                        data.get("captions") or data.get("transcript") or []
                    )
                    counts["captions"] += len(
                        [c for c in items if c.get("text", "").strip()]
                    )
                except Exception:
                    pass

            elif ft in (FileType.audio, FileType.video):
                counts["media"] += 1

            counts["meetings"].add(mid)

    counts["meetings"] = len(counts["meetings"])
    return counts

  
def _count_db(session: Session) -> dict:
    return {
        "meetings":    session.exec(select(func.count(Meeting.id))).one(),
        "summaries":   session.exec(select(func.count(Summary.id))).one(),
        "transcripts": session.exec(select(func.count(TranscriptTurn.id))).one(),
        "captions":    session.exec(select(func.count(Caption.id))).one(),
        "media":       session.exec(select(func.count(MediaFile.id))).one(),
    }


def run_backfill():
    organized = Path(settings.ORGANIZED_DATA_DIR)
    if not organized.exists():
        print("❌ Organized directory not found.")
        return

    date_folders = sorted(
        [f for f in organized.iterdir() if f.is_dir()]
    )

    ok = skipped = failed = 0

    with Session(engine) as session:
        for batch_start in range(0, len(date_folders), BATCH_SIZE):
            batch = date_folders[batch_start: batch_start + BATCH_SIZE]

            for date_folder in batch:
                date = date_folder.name

                # Group files by meeting_id
                meeting_map: dict[str, list[Path]] = {}
                memory_files: list[Path] = []          # ← collect separately
                    
                for f in date_folder.iterdir():
                    # Skip loose summary.json and memory files (handled separately)
                    if f.name == "summary.json":
                        continue
                    # Memory files get their own route
                    if f.name.startswith("meet-memory") and f.suffix == ".json":
                        continue
                    ft = _detect_file_type(f.name)
                    mid = _extract_meeting_id(f.name)
                    meeting_map.setdefault(mid, []).append(f)
                    
                    # collect webm files that have no valid meeting ID
                    if ft in _FTYPE_MAP and not _MEETING_ID_RE.match(mid):
                        orphan_media.append((f, _FTYPE_MAP[ft]))

                # attach orphan media to the first valid meeting in this date folder
                valid_meetings = [
                    mid for mid in meeting_map
                    if _MEETING_ID_RE.match(mid)
                ]
                if orphan_media and valid_meetings:
                    meeting_map[valid_meetings[0]].extend(
                        [f for f, _ in orphan_media]
                    )
                
                for meeting_id, files in meeting_map.items():
                    summary_json = []
                    captions_and_transcripts = []
                    transcript_json = []
                    captions_json = []
                    media_files = []

                    print(f"📦 Building grouped payloads for {date}/{meeting_id} | total_files={len(files)}")

                    for f in files:
                        ft = _detect_file_type(f.name)
                        print(f"   📄 file={f.name} | detected_type={ft}")

                        if ft == FileType.summary:
                            raw = _load_json(f)
                            if raw is not None:
                                summary_json.append((f, raw))
                                print(f"   🧠 grouped summary file -> {f.name}")
                            else:
                                print(f"   ⚠️ summary file unreadable/skipped -> {f.name}")

                        elif ft == FileType.captions_and_transcripts:
                            raw = _load_json(f)
                            if raw is not None:
                                captions_and_transcripts.append((f, raw))
                                print(f"   📝 grouped captions_and_transcripts file -> {f.name}")
                            else:
                                print(f"   ⚠️ captions_and_transcripts unreadable/skipped -> {f.name}")

                        elif ft == FileType.transcript:
                            raw = _load_json(f)
                            if raw is not None:
                                transcript_json.append((f, raw))
                                print(f"   📜 grouped transcript file -> {f.name}")
                            else:
                                print(f"   ⚠️ transcript file unreadable/skipped -> {f.name}")

                        elif ft == FileType.captions:
                            raw = _load_json(f)
                            if raw is not None:
                                captions_json.append((f, raw))
                                print(f"   💬 grouped captions file -> {f.name}")
                            else:
                                print(f"   ⚠️ captions file unreadable/skipped -> {f.name}")

                        elif ft in _FTYPE_MAP:
                            media_files.append((f, _FTYPE_MAP[ft]))
                            print(f"   🎥 grouped media file -> {f.name} | media_type={_FTYPE_MAP[ft]}")

                    print(
                        f"   📊 grouped counts"
                        f" | summaries={len(summary_json)}"
                        f" | captions_and_transcripts={len(captions_and_transcripts)}"
                        f" | transcripts={len(transcript_json)}"
                        f" | captions={len(captions_json)}"
                        f" | media={len(media_files)}"
                    )

                    try:
                        result = migrate_meeting_folder(
                            session=session,
                            meeting_id=meeting_id,
                            date=date,
                            summary_json=summary_json,
                            captions_and_transcripts=captions_and_transcripts,
                            transcript_json=transcript_json,
                            captions_json=captions_json,
                            media_files=media_files,
                        )
                        if result:
                            print(f"  ✓ {date}/{meeting_id}")
                            ok += 1
                        else:
                            print(f"  ⚠️  {date}/{meeting_id} — invalid ID, skipped")
                            skipped += 1
                    except Exception as e:
                        session.rollback()
                        print(f"  ❌ {date}/{meeting_id} — {e}")
                        failed += 1


                # Process memory files separately
                if memory_files:
                    print(f"🧠 Preparing memory files for {date} | count={len(memory_files)}")

                    memory_groups: dict[str, list[Path]] = {}

                    for f in memory_files:
                        mem_meeting_id = _generate_mem_meeting_id(f.name)
                        memory_groups.setdefault(mem_meeting_id, []).append(f)
                        print(f"   📄 memory candidate: {f.name} -> group={mem_meeting_id}")

                    for mem_meeting_id, grouped_files in memory_groups.items():
                        try:
                            print(
                                f"   📦 memory group ready: {mem_meeting_id} "
                                f"| files={len(grouped_files)}"
                            )
                            result = migrate_memory_file(
                                session=session,
                                filepath=grouped_files,
                                date=date,
                            )

                            if result:
                                print(
                                    f"  ✓ {date}/{mem_meeting_id} "
                                    f"→ {result.meeting_id} | grouped_files={len(grouped_files)}"
                                )
                                ok += 1
                            else:
                                print(
                                    f"  ⚠️  {date}/{mem_meeting_id} "
                                    f"— grouped memory files skipped"
                                )
                                skipped += 1

                        except Exception as e:
                            session.rollback()
                            print(f"  ❌ {date}/{mem_meeting_id} — {e}")
                            failed += 1
                            
            
            # Commit every BATCH_SIZE date folders
            session.commit()
            print(f"── committed batch ending {batch[-1].name} ──")

        # ── Verification report ────────────────────────────────────────
        print("\n── Verification report ──────────────────────────────────")
        disk  = _count_folder_files(organized)
        db    = _count_db(session)

        # Add db_memory count before the report
        db_memory = session.exec(
            select(func.count(Meeting.id)).where(Meeting.meeting_id.like("mem-%"))
        ).one()
        all_match = True
        # meetings is approximate (meeting_id parsing isn't perfect on disk)
        # so we report but don't flag it as a mismatch
        rows = [
            ("summaries",        disk["summaries"],   db["summaries"],   None),
            ("transcript turns", disk["transcripts"],  db["transcripts"], None),
            ("caption rows",     disk["captions"],     db["captions"],    None),
            ("media files",      disk["media"],        db["media"],       None),
            ("memory imports",   disk["memory"],       db_memory,         None),
        ]

        for label, d, b, _ in rows:
            if d == b:
                status = "✓"
                note = "exact match"
            elif b > d:
                status = "~"   # db higher — could be duplicate meetings across dates
                note = f"db has {b - d} more rows"
            else:
                status = "✗"   # disk higher — means some files weren't migrated
                note = f"disk has {d - b} unmigrated rows"
            print(f"  {status}  {label:20s}  disk={d}  db={b}  ({note})")
            
        print()
        print(f"  Migrated: {ok}  |  Skipped: {skipped}  |  Failed: {failed}")
        if all_match:
            print("\n  ✅ All counts match. Safe to delete JSON files.")
        else:
            print("\n  ⚠️  Counts differ. Do not delete files yet.")

        # Count actual mismatches — exclude media (db higher is expected for media)
        hard_mismatches = [
            (label, d, b) for label, d, b, _ in rows
            if label != "media files" and d != b
        ]

        if not hard_mismatches:
            print("\n  ✅ All counts match. Safe to delete JSON files.")
        else:
            print(f"\n  ⚠️  {len(hard_mismatches)} mismatch(es). Do not delete files yet.")
        print("─────────────────────────────────────────────────────────\n")

""" 

"""
def _resolve_target_date_folders(organized: Path, folder_names: list[str]) -> list[Path]:
    """
    Return only existing, exact-match date folders requested by the caller.
    Raises if any requested folder does not exist.
    """
    requested = {name.strip() for name in folder_names if name and name.strip()}
    if not requested:
        raise ValueError("No folder names provided.")

    available = {
        f.name: f for f in organized.iterdir() if f.is_dir()
    }

    missing = sorted([name for name in requested if name not in available])
    if missing:
        raise ValueError(f"Requested folder(s) not found: {', '.join(missing)}")

    selected = [available[name] for name in sorted(requested)]

    print(f"🎯 Selected folders for scoped backfill: {', '.join([f.name for f in selected])}")
    return selected

def run_backfill_for_folders(folder_names: list[str]):
    organized = Path(settings.ORGANIZED_DATA_DIR)
    if not organized.exists():
        print("❌ Organized directory not found.")
        return

    try:
        date_folders = _resolve_target_date_folders(organized, folder_names)
    except Exception as e:
        print(f"❌ Folder selection failed: {e}")
        return

    ok = skipped = failed = 0

    print(f"🚀 Starting scoped backfill | folder_count={len(date_folders)}")

    with Session(engine) as session:
        for batch_start in range(0, len(date_folders), BATCH_SIZE):
            batch = date_folders[batch_start: batch_start + BATCH_SIZE]
            print(
                f"\n📦 Scoped batch start | batch_start={batch_start} "
                f"| batch_size={len(batch)}"
            )

            for date_folder in batch:
                date = date_folder.name
                print(f"\n📂 Processing selected folder: {date}")

                # Group files by meeting_id
                meeting_map: dict[str, list[Path]] = {}
                memory_files: list[Path] = []

                scoped_orphan_media: list[tuple[Path, FileTypeEnum]] = []

                for f in date_folder.iterdir():
                    if f.name == "summary.json":
                        continue

                    if f.name.startswith("meet-memory") and f.suffix == ".json":
                        continue

                    ft = _detect_file_type(f.name)
                    mid = _extract_meeting_id(f.name)
                    meeting_map.setdefault(mid, []).append(f)

                    # collect webm files that have no valid meeting ID
                    if ft in _FTYPE_MAP and not _MEETING_ID_RE.match(mid):
                        scoped_orphan_media.append((f, _FTYPE_MAP[ft]))
                        print(f"   🎥 orphan media detected -> {f.name}")

                # attach orphan media to the first valid meeting in this date folder
                valid_meetings = [
                    mid for mid in meeting_map
                    if _MEETING_ID_RE.match(mid)
                ]

                if scoped_orphan_media and valid_meetings:
                    meeting_map[valid_meetings[0]].extend(
                        [f for f, _ in scoped_orphan_media]
                    )
                    print(
                        f"   🔗 attached orphan media count={len(scoped_orphan_media)} "
                        f"to meeting={valid_meetings[0]}"
                    )

                print(
                    f"🧭 Folder map ready | date={date} "
                    f"| meetings={len(meeting_map)} | memory_files={len(memory_files)}"
                )

                for meeting_id, files in meeting_map.items():
                    summary_json = []
                    captions_and_transcripts = []
                    transcript_json = []
                    captions_json = []
                    media_files = []

                    print(f"📦 Building grouped payloads for {date}/{meeting_id} | total_files={len(files)}")

                    for f in files:
                        ft = _detect_file_type(f.name)
                        print(f"   📄 file={f.name} | detected_type={ft}")

                        if ft == FileType.summary:
                            raw = _load_json(f)
                            if raw is not None:
                                summary_json.append((f, raw))
                                print(f"   🧠 grouped summary file -> {f.name}")
                            else:
                                print(f"   ⚠️ summary file unreadable/skipped -> {f.name}")

                        elif ft == FileType.captions_and_transcripts:
                            raw = _load_json(f)
                            if raw is not None:
                                captions_and_transcripts.append((f, raw))
                                print(f"   📝 grouped captions_and_transcripts file -> {f.name}")
                            else:
                                print(f"   ⚠️ captions_and_transcripts unreadable/skipped -> {f.name}")

                        elif ft == FileType.transcript:
                            raw = _load_json(f)
                            if raw is not None:
                                transcript_json.append((f, raw))
                                print(f"   📜 grouped transcript file -> {f.name}")
                            else:
                                print(f"   ⚠️ transcript file unreadable/skipped -> {f.name}")

                        elif ft == FileType.captions:
                            raw = _load_json(f)
                            if raw is not None:
                                captions_json.append((f, raw))
                                print(f"   💬 grouped captions file -> {f.name}")
                            else:
                                print(f"   ⚠️ captions file unreadable/skipped -> {f.name}")

                        elif ft in _FTYPE_MAP:
                            media_files.append((f, _FTYPE_MAP[ft]))
                            print(f"   🎥 grouped media file -> {f.name} | media_type={_FTYPE_MAP[ft]}")

                    print(
                        f"   📊 grouped counts"
                        f" | summaries={len(summary_json)}"
                        f" | captions_and_transcripts={len(captions_and_transcripts)}"
                        f" | transcripts={len(transcript_json)}"
                        f" | captions={len(captions_json)}"
                        f" | media={len(media_files)}"
                    )

                    try:
                        result = migrate_meeting_folder(
                            session=session,
                            meeting_id=meeting_id,
                            date=date,
                            summary_json=summary_json,
                            captions_and_transcripts=captions_and_transcripts,
                            transcript_json=transcript_json,
                            captions_json=captions_json,
                            media_files=media_files,
                        )
                        if result:
                            print(f"  ✓ {date}/{meeting_id}")
                            ok += 1
                        else:
                            print(f"  ⚠️  {date}/{meeting_id} — invalid ID, skipped")
                            skipped += 1
                    except Exception as e:
                        session.rollback()
                        print(f"  ❌ {date}/{meeting_id} — {e}")
                        failed += 1

                # Process memory files separately
                if memory_files:
                    print(f"🧠 Preparing memory files for {date} | count={len(memory_files)}")

                    memory_groups: dict[str, list[Path]] = {}

                    for f in memory_files:
                        mem_meeting_id = _generate_mem_meeting_id(f.name)
                        memory_groups.setdefault(mem_meeting_id, []).append(f)
                        print(f"   📄 memory candidate: {f.name} -> group={mem_meeting_id}")

                    for mem_meeting_id, grouped_files in memory_groups.items():
                        try:
                            print(
                                f"   📦 memory group ready: {mem_meeting_id} "
                                f"| files={len(grouped_files)}"
                            )
                            result = migrate_memory_file(
                                session=session,
                                filepath=grouped_files,
                                date=date,
                            )

                            if result:
                                print(
                                    f"  ✓ {date}/{mem_meeting_id} "
                                    f"→ {result.meeting_id} | grouped_files={len(grouped_files)}"
                                )
                                ok += 1
                            else:
                                print(
                                    f"  ⚠️  {date}/{mem_meeting_id} "
                                    f"— grouped memory files skipped"
                                )
                                skipped += 1

                        except Exception as e:
                            session.rollback()
                            print(f"  ❌ {date}/{mem_meeting_id} — {e}")
                            failed += 1

            session.commit()
            print(f"── committed selected batch ending {batch[-1].name} ──")

    print("\n── Scoped backfill complete ─────────────────────────────")
    print(f"  Migrated: {ok}  |  Skipped: {skipped}  |  Failed: {failed}")
    print("─────────────────────────────────────────────────────────\n")

if __name__ == "__main__":
    run_backfill()
    run_backfill_for_folders([
        "2026-04-01",
        "2026-04-02",
    ])