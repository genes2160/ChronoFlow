# app/api/services/migration_service.py
"""
ChronoFlow — JSON → Postgres migration service
Idempotent. Safe to re-run. Validates before inserting.
"""

import json
import hashlib
import re
from pathlib import Path
from app.api.schema.schemas import FileType
from sqlmodel import Session, select
from app.api.models.model import (
    Meeting, Summary, ParticipantScore,
    TranscriptTurn, Caption, MediaFile, FileTypeEnum
)

# Replace the strict regex with one that accepts both formats
_MEETING_ID_RE = re.compile(
    r'^[a-z]{3}-[a-z]{4}-[a-z]{3}(?:-\d{4}-\d{2}-\d{2})?$'   # hrp-axdm-gqm or hrp-axdm-gqm-2026-03-20
    r'|^Meet[_–-].+(?:-\d{4}-\d{2}-\d{2})?$'                 # Meet_Team_Sync or Meet_Team_Sync-2026-03-20
    r'|^mem-[a-f0-9]{8}(?:-\d{4}-\d{2}-\d{2})?$'             # mem-0bb62959 or mem-0bb62959-2026-03-20
    r'|^ts-[a-f0-9]{8}(?:-\d{4}-\d{2}-\d{2})?$'              # ts-a3f9b2c1 or ts-a3f9b2c1-2026-03-20
    r'|^unk-[a-f0-9]{8}(?:-\d{4}-\d{2}-\d{2})?$'             # unk-xxxxxxxx or unk-xxxxxxxx-2026-03-20
)

# NEW: add near helpers in migration_service.py
def _as_file_payload_list(value):
    """
    Normalizes incoming payload into a list.

    Supports:
    - None
    - single raw payload
    - [(Path, raw), ...]
    - [raw1, raw2, ...]
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def _split_payload_and_path(item):
    """
    Returns: (path, raw)
    Supports:
    - raw
    - (Path, raw)
    """
    if (
        isinstance(item, tuple)
        and len(item) == 2
        and isinstance(item[0], Path)
    ):
        return item[0], item[1]

    return None, item


def _dedupe_and_sort_file_payloads(items):
    """
    For payloads backed by files:
    - remove true duplicates using size + hash
    - sort continuations by modified time

    For raw-only payloads (no Path), preserve order as received.
    """
    normalized = _as_file_payload_list(items)
    file_backed = []
    raw_only = []

    for item in normalized:
        path, raw = _split_payload_and_path(item)
        if path is None:
            raw_only.append((None, raw))
        else:
            file_backed.append((path, raw))

    seen = set()
    unique = []

    for path, raw in file_backed:
        try:
            stat = path.stat()
            file_hash = hashlib.md5(path.read_bytes()).hexdigest()
            key = (stat.st_size, file_hash)
        except Exception:
            # if file inspection fails, keep it rather than losing data
            key = ("__fallback__", str(path.resolve()))

        if key in seen:
            continue
        seen.add(key)
        unique.append((path, raw))

    unique.sort(key=lambda x: x[0].stat().st_mtime)

    # raw-only values are appended in the same order received
    return unique + raw_only


# ── 1. Meeting anchor ──────────────────────────────────────────────────────

def upsert_meeting(session: Session, meeting_id: str, date: str) -> Meeting | None:
    """Returns None if meeting_id looks like a parser fallback."""
    if not _MEETING_ID_RE.match(meeting_id):
        return None

    existing = session.exec(
        select(Meeting).where(Meeting.meeting_id == meeting_id)
    ).first()
    if existing:
        return existing  # ← already exists, nothing to do

    meeting = Meeting(meeting_id=meeting_id, date=date)
    session.add(meeting)
    session.flush()
    return meeting


# ── 2. Summary + ParticipantScores ────────────────────────────────────────

def migrate_summary(session: Session, meeting: Meeting, raw: dict) -> None:
    # Guard: summary already migrated
    if session.exec(
        select(Summary).where(Summary.meeting_id == meeting.id)
    ).first():
        return

    response = raw.get("response", raw)
    overview = response.get("meeting_overview", {})
    scoring  = response.get("scoring", {})
    theme    = response.get("meeting_theme", {})
    overall  = response.get("overall_summary", {})

    session.add(Summary(
        meeting_id=meeting.id,
        raw_json=response,
        overall_effectiveness=overall.get("overall_effectiveness"),
        primary_theme=theme.get("primary_theme"),
    ))

    meeting.duration_minutes = overview.get("duration_minutes")
    meeting.has_summary = True
    session.add(meeting)

    # Guard each participant score individually to survive partial re-runs
    for name, s in scoring.get("participants", {}).items():
        already = session.exec(
            select(ParticipantScore).where(
                ParticipantScore.meeting_id == meeting.id,
                ParticipantScore.name == name,
            )
        ).first()
        if already:
            continue

        session.add(ParticipantScore(
            meeting_id=meeting.id,
            name=name,
            participation=s.get("participation"),
            clarity=s.get("clarity"),
            technical=s.get("technical"),
            communication=s.get("communication"),
            leadership=s.get("leadership"),
            weighted_score=s.get("weighted_score"),
            rank=s.get("rank"),
        ))


# ── 3. TranscriptTurns ────────────────────────────────────────────────────

def migrate_transcript(session: Session, meeting: Meeting, raw: dict | list) -> None:
    print(f"📜 migrate_transcript → meeting={meeting.id}")

    # handle plain list OR {"transcripts": [...]} shape
    if isinstance(raw, list):
        turns_raw = raw
    elif isinstance(raw, dict):
        turns_raw = raw.get("transcripts") or raw.get("transcript") or []
    else:
        print(f"⚠️ migrate_transcript invalid raw shape for meeting={meeting.id}")
        return

    print(f"📥 transcript raw rows={len(turns_raw)}")

    # NEW: append-safe idempotency guard using row signatures,
    # not a blanket "any rows exist => return"
    existing_rows = session.exec(
        select(
            TranscriptTurn.speaker,
            TranscriptTurn.text,
            TranscriptTurn.timestamp,
            TranscriptTurn.relative_time,
        ).where(TranscriptTurn.meeting_id == meeting.id)
    ).all()

    existing_signatures = set(existing_rows)
    print(f"🛡 existing transcript signatures={len(existing_signatures)}")

    turns = []

    for i, t in enumerate(turns_raw):
        if not isinstance(t, dict):
            print(f"⚠️ skipping non-dict transcript row index={i}")
            continue

        speaker = clean_speaker(t.get("speaker"))
        text = clean_text(t.get("text"))
        timestamp = t.get("timestamp")
        relative_time = t.get("relativeTime")

        if not text:
            print(f"⚠️ skipping empty transcript text index={i}")
            continue

        signature = (speaker, text, timestamp, relative_time)
        if signature in existing_signatures:
            print(f"⏭ transcript row already exists index={i}")
            continue

        # Keep current behavior, but be more tolerant if id is absent
        turn_id = t.get("id")
        if turn_id is None:
            turn_id = timestamp if timestamp is not None else i

        turns.append(
            TranscriptTurn(
                meeting_id=meeting.id,
                turn_id=turn_id,
                speaker=speaker,
                text=text,
                timestamp=timestamp,
                relative_time=relative_time,
                confidence=t.get("confidence"),
                word_count=t.get("wordCount"),
            )
        )

        existing_signatures.add(signature)

    print(f"🧾 transcript rows to insert={len(turns)}")

    if turns:
        session.bulk_save_objects(turns)
        meeting.has_transcript = True
        session.add(meeting)
        print(f"✅ inserted transcript rows for meeting={meeting.id}")
    else:
        print(f"⚠️ no new transcript rows to insert for meeting={meeting.id}")

# ── 4. Captions ───────────────────────────────────────────────────────────

def migrate_captions(session: Session, meeting: Meeting, raw: list | dict) -> None:
    print(f"💬 migrate_captions → meeting={meeting.id}")

    items: list = raw if isinstance(raw, list) else (
        raw.get("captions") or raw.get("transcript") or []
    )

    print(f"📥 caption raw rows={len(items)}")

    # NEW: append-safe idempotency guard using row signatures,
    # not a blanket "any rows exist => return"
    existing_rows = session.exec(
        select(
            Caption.speaker,
            Caption.text,
            Caption.ts,
        ).where(Caption.meeting_id == meeting.id)
    ).all()

    existing_signatures = set(existing_rows)
    print(f"🛡 existing caption signatures={len(existing_signatures)}")

    captions = []

    for i, c in enumerate(items):
        if not isinstance(c, dict):
            print(f"⚠️ skipping non-dict caption row index={i}")
            continue

        speaker = clean_speaker(c.get("speaker"))
        text = clean_text(c.get("text"))
        ts = c.get("ts")

        if not text:
            print(f"⚠️ skipping empty caption text index={i}")
            continue

        signature = (speaker, text, ts)
        if signature in existing_signatures:
            print(f"⏭ caption row already exists index={i}")
            continue

        captions.append(
            Caption(
                meeting_id=meeting.id,
                speaker=speaker,
                text=text,
                ts=ts,
            )
        )
        existing_signatures.add(signature)

    print(f"🧾 caption rows to insert={len(captions)}")

    if captions:
        session.bulk_save_objects(captions)
        meeting.has_captions = True
        session.add(meeting)
        print(f"✅ inserted caption rows for meeting={meeting.id}")
    else:
        print(f"⚠️ no new caption rows to insert for meeting={meeting.id}")

# ── 5. Captions and transcripts ───────────────────────────────────────────────────────────
def migrate_captions_and_transcripts(session: Session, meeting: Meeting, raw: dict) -> None:
    try:
        print(f"▶ Processing meeting {meeting.id}")

        # NEW: do not blanket-skip just because rows already exist.
        # Instead inspect existing rows and append only new ones.
        has_turns = session.exec(
            select(TranscriptTurn.id).where(TranscriptTurn.meeting_id == meeting.id)
        ).first()

        has_captions = session.exec(
            select(Caption.id).where(Caption.meeting_id == meeting.id)
        ).first()

        print(
            f"🛡 Existing meeting state → has_turns={bool(has_turns)} "
            f"| has_captions={bool(has_captions)}"
        )

        print(f"📝 Updating meeting metadata {meeting.id}")
        update_meeting_from_raw(meeting, raw)

        captions_data = raw.get("captions", [])
        transcript_data = raw.get("transcripts", {}).get("transcripts", [])

        print(f"📥 Raw transcript count: {len(transcript_data)}")
        print(f"📥 Raw captions count: {len(captions_data)}")

        # Existing transcript signatures
        existing_transcript_rows = session.exec(
            select(
                TranscriptTurn.speaker,
                TranscriptTurn.text,
                TranscriptTurn.timestamp,
                TranscriptTurn.relative_time,
            ).where(TranscriptTurn.meeting_id == meeting.id)
        ).all()
        existing_transcript_signatures = set(existing_transcript_rows)

        print(f"🛡 Existing transcript signatures: {len(existing_transcript_signatures)}")

        # Existing caption signatures
        existing_caption_rows = session.exec(
            select(
                Caption.speaker,
                Caption.text,
                Caption.ts,
            ).where(Caption.meeting_id == meeting.id)
        ).all()
        existing_caption_signatures = set(existing_caption_rows)

        print(f"🛡 Existing caption signatures: {len(existing_caption_signatures)}")

        # ── Build Transcript Turns ─────────────────────────────
        turns = []
        for i, t in enumerate(transcript_data):
            try:
                if not isinstance(t, dict):
                    print(f"⚠️ Skipping non-dict transcript at index {i}")
                    continue

                speaker = clean_speaker(t.get("speaker"))
                text = clean_text(t.get("text"))
                timestamp = t.get("timestamp")
                relative_time = t.get("relativeTime")

                if not text:
                    print(f"⚠️ Empty text at transcript index {i}")
                    continue

                signature = (speaker, text, timestamp, relative_time)
                if signature in existing_transcript_signatures:
                    print(f"⏭ Skipping existing transcript signature at index {i}")
                    continue

                turn_id = t.get("id")
                if turn_id is None:
                    turn_id = timestamp if timestamp is not None else i

                turns.append(
                    TranscriptTurn(
                        meeting_id=meeting.id,
                        turn_id=turn_id,
                        speaker=speaker,
                        text=text,
                        timestamp=timestamp,
                        relative_time=relative_time,
                        confidence=t.get("confidence"),
                        word_count=t.get("wordCount"),
                    )
                )

                existing_transcript_signatures.add(signature)

            except Exception as loop_err:
                print(f"❌ Error in transcript loop index {i}: {str(loop_err)}")

        print(f"🧾 Transcript turns to insert: {len(turns)}")

        # ── Build Captions ─────────────────────────────
        captions = []
        for i, c in enumerate(captions_data):
            try:
                if not isinstance(c, dict):
                    print(f"⚠️ Skipping non-dict caption at index {i}")
                    continue

                speaker = clean_speaker(c.get("speaker"))
                text = clean_text(c.get("text"))
                ts = c.get("ts")

                if not text:
                    print(f"⚠️ Empty caption text at index {i}")
                    continue

                signature = (speaker, text, ts)
                if signature in existing_caption_signatures:
                    print(f"⏭ Skipping existing caption signature at index {i}")
                    continue

                captions.append(
                    Caption(
                        meeting_id=meeting.id,
                        speaker=speaker,
                        text=text,
                        ts=ts,
                    )
                )

                existing_caption_signatures.add(signature)

            except Exception as loop_err:
                print(f"❌ Error in caption loop index {i}: {str(loop_err)}")

        print(f"💬 Captions to insert: {len(captions)}")

        # ── Bulk Insert ─────────────────────────────
        if turns:
            session.bulk_save_objects(turns)
            print(f"✅ Inserted transcript turns for meeting {meeting.id}")

        if captions:
            session.bulk_save_objects(captions)
            print(f"✅ Inserted captions for meeting {meeting.id}")

        # ── Update Meeting Flags ─────────────────────
        if turns:
            meeting.has_transcript = True

        if captions:
            meeting.has_captions = True

        session.add(meeting)
        session.commit()
        print(f"💾 Commit successful for meeting {meeting.id}")

    except Exception as err:
        session.rollback()
        print(f"❌ ERROR processing meeting {meeting.id}: {str(err)}")
        print(f"↩️ Rolled back meeting {meeting.id}")
        pass

# ── 6. MediaFile ──────────────────────────────────────────────────────────
def migrate_media_file(
    session: Session,
    meeting: Meeting,
    filepath: Path,
    file_type: FileTypeEnum,
) -> None:
    migrate_file_record(session, meeting, filepath, file_type)

    if file_type == FileTypeEnum.audio:
        meeting.has_audio = True
    elif file_type == FileTypeEnum.video:
        meeting.has_video = True

    session.add(meeting)
    

# ── Helpers ───────────────────────────────────────────────────────────────
def update_meeting_from_raw(meeting: Meeting, raw: dict):
    try:
        print(f"📝 update_meeting_from_raw → Meeting {meeting.id}")

        meeting.meeting_name = raw.get("meeting_name")
        print(f"   meeting_name: {meeting.meeting_name}")

        meta = raw.get("transcripts", {}).get("metadata", {})
        summary = raw.get("transcripts", {}).get("summary", {})

        meeting.start_time = meta.get("startTime")
        print(f"   start_time: {meeting.start_time}")

        meeting.end_time = meta.get("endTime")
        print(f"   end_time: {meeting.end_time}")

        meeting.duration_ms = meta.get("duration")
        print(f"   duration_ms: {meeting.duration_ms}")

        meeting.attendee_count = meta.get("attendeeCount")
        print(f"   attendee_count: {meeting.attendee_count}")

        meeting.total_words = summary.get("totalWords")
        print(f"   total_words: {meeting.total_words}")

        meeting.avg_confidence = summary.get("averageConfidence")
        print(f"   avg_confidence: {meeting.avg_confidence}")

        if meeting.duration_ms and not meeting.duration_minutes:
            meeting.duration_minutes = int(meeting.duration_ms / 60000)
            print(f"   duration_minutes (calculated): {meeting.duration_minutes}")
        else:
            print(f"   duration_minutes (existing): {meeting.duration_minutes}")

    except Exception as err:
        print(f"❌ update_meeting_from_raw {str(err)}")
        pass
        
def clean_speaker(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip()
    if name.lower() in {"unknown", "you", ""}:
        return None
    return name


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())

   
def _detect_file_type(filename: str) -> FileType:
    name = filename.lower()
    if "summary" in name and name.endswith(".json"):
        return FileType.summary
    if ("caption" in name or "captions" in name) and name.endswith(".json"):
        return FileType.captions
    if "transcript" in name and name.endswith(".json"):
        return FileType.transcript
    if name.endswith(".webm"):
        return FileType.audio if "audio" in name else FileType.video
    return FileType.unknown


def _extract_meeting_id(filename: str) -> str:
    # Format 1: xxx-xxxx-xxx  e.g. hrp-axdm-gqm
    match = re.search(r'([a-z]{3}-[a-z]{4}-[a-z]{3})', filename)
    if match:
        return match.group(1)

    # Format 2: Meet_ or Meet– or Meet- prefix (named meetings)
    # em dash \u2013 must be escaped explicitly, not in a character class range
    match = re.search(r'(Meet(?:_|\u2013|-).+?)(?:\.json|\.webm|--|\Z)', filename, re.IGNORECASE)
    if match:
        return match.group(1)

    # Format 3: meet_captions_<ts> or meet_transcript_<ts>
    match = re.search(r'meet[_-](?:captions|transcript|recording)[_-](\d+)', filename, re.IGNORECASE)
    if match:
        h = hashlib.md5(match.group(1).encode()).hexdigest()[:8]
        return f"ts-{h}"

    # Fallback: generate a deterministic ID based on the filename hash
    h = hashlib.md5(filename.encode()).hexdigest()[:8]
    return f"unk-{h}"


def _generate_mem_meeting_id(filename: str) -> str:
    """
    Deterministic meeting ID from filename.
    Always starts with 'mem-' as the distinguishing signature.
    e.g. mem-a3f9b2c1
    Re-running with same file always produces same ID.
    """
    h = hashlib.md5(filename.encode()).hexdigest()[:8]
    return f"mem-{h}"


def _load_json_file(filepath: Path) -> dict | list | None:
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── 6. Memory files ───────────────────────────────────────────────────────

def migrate_memory_file(
    session: Session,
    filepath: Path | list[Path],
    date: str,
) -> Meeting | None:
    """
    Handles meet-memory-*.json files.

    Supports:
    - single Path
    - grouped list[Path]

    Rules:
    - same size + same hash => true duplicate => keep one
    - different size/hash => continuation => sort by modified time
    - process grouped files in order on first migration
    - if captions already exist for this memory meeting, skip whole group on re-run
    """
    filepaths = filepath if isinstance(filepath, list) else [filepath]

    if not filepaths:
        print("⚠️ migrate_memory_file → empty filepath list")
        return None

    print(f"🧠 migrate_memory_file → incoming_files={len(filepaths)} | date={date}")

    # Deterministic anchor from first file in the grouped batch
    anchor = filepaths[0]
    base_meeting_id = _generate_mem_meeting_id(anchor.name)
    meeting_id = f"{base_meeting_id}-{date}"
    print(
        f"🪪 memory anchor={anchor.name} "
        f"→ base_meeting_id={base_meeting_id} "
        f"→ dated_meeting_id={meeting_id}"
    )

    existing = session.exec(
        select(Meeting).where(Meeting.meeting_id == meeting_id)
    ).first()

    if existing:
        meeting = existing
        print(f"♻️ existing memory meeting found → db_id={meeting.id}")
    else:
        meeting = Meeting(
            meeting_id=meeting_id,
            date=date,
            duration_minutes=10,
            has_captions=False,
        )
        session.add(meeting)
        session.flush()
        print(f"✅ created memory meeting → db_id={meeting.id}")

    # Keep re-run idempotency: if this grouped memory meeting already has captions,
    # assume it was already migrated and skip.
    if session.exec(
        select(Caption.id).where(Caption.meeting_id == meeting.id)
    ).first():
        print(f"⏭ memory meeting already has captions → skip meeting_id={meeting_id}")
        return meeting

    # Dedupe exact same files, keep different ones as continuations
    seen = set()
    ordered_unique_files: list[Path] = []

    for f in filepaths:
        try:
            stat = f.stat()
            file_hash = hashlib.md5(f.read_bytes()).hexdigest()
            key = (stat.st_size, file_hash)
            print(
                f"📦 memory candidate={f.name} "
                f"| size={stat.st_size} | hash={file_hash[:12]}..."
            )
        except Exception as err:
            print(f"❌ memory file inspection failed → {f} | err={err}")
            continue

        if key in seen:
            print(f"⏭ duplicate memory file skipped → {f.name}")
            continue

        seen.add(key)
        ordered_unique_files.append(f)

    ordered_unique_files.sort(key=lambda p: p.stat().st_mtime)

    print(
        "🧾 memory files after dedupe/order → "
        + ", ".join([f"{f.name}@{int(f.stat().st_mtime)}" for f in ordered_unique_files])
    )

    inserted_count = 0

    for index, f in enumerate(ordered_unique_files, start=1):
        print(f"📥 processing memory part {index}/{len(ordered_unique_files)} → {f.name}")

        raw = _load_json_file(f)
        if not raw:
            print(f"⚠️ memory file unreadable/empty → {f.name}")
            continue

        items = raw if isinstance(raw, list) else raw.get("transcript", [])
        if not isinstance(items, list):
            print(f"⚠️ memory file transcript shape invalid → {f.name}")
            continue

        captions = [
            Caption(
                meeting_id=meeting.id,
                speaker=c.get("user") or c.get("speaker") or None,
                text=c.get("content") or c.get("text", ""),
                ts=None,
            )
            for c in items
            if (c.get("content") or c.get("text", "")).strip()
        ]

        if not captions:
            print(f"⚠️ no usable memory captions found → {f.name}")
            continue

        session.bulk_save_objects(captions)
        inserted_count += len(captions)

        print(
            f"✅ appended memory captions → file={f.name} "
            f"| rows_added={len(captions)} | running_total={inserted_count}"
        )

    if inserted_count > 0:
        meeting.has_captions = True
        session.add(meeting)
        print(f"💾 memory meeting updated → db_id={meeting.id} | inserted_count={inserted_count}")
    else:
        print(f"⚠️ memory meeting had no new caption rows → db_id={meeting.id}")

    return meeting

def migrate_file_record(
    session: Session,
    meeting: Meeting,
    filepath: Path,
    file_type: FileTypeEnum,
) -> None:
    """
    Catalog any source file (summary / captions / transcript / audio / video)
    into the meeting file inventory table.

    Safe to re-run.
    """
    if session.exec(
        select(MediaFile).where(
            MediaFile.meeting_id == meeting.id,
            MediaFile.filename == filepath.name,
        )
    ).first():
        print(f"⏭ file record already exists -> {filepath.name}")
        return

    stat = filepath.stat() if filepath.exists() else None

    session.add(MediaFile(
        meeting_id=meeting.id,
        filename=filepath.name,
        file_type=file_type,
        size_bytes=stat.st_size if stat else None,
        storage_url=str(filepath.resolve()),
        storage_backend="local",
        uploaded_by=None,
    ))

    print(f"📎 catalogued file record -> {filepath.name} ({file_type})")
    

# ── Orchestrator ──────────────────────────────────────────────────────────

def migrate_meeting_folder(
    session: Session,
    meeting_id: str,
    date: str,
    captions_and_transcripts: dict | list | None = None,
    summary_json: dict | list | None = None,
    transcript_json: dict | list | None = None,
    captions_json: list | dict | None = None,
    media_files: list[tuple[Path, FileTypeEnum]] | None = None,
) -> Meeting | None:
    print(f"📁 migrate_meeting_folder → meeting_id={meeting_id}, date={date}")

    dated_meeting_id = f"{meeting_id}-{date}"
    print(f"🪪 dated_meeting_id={dated_meeting_id}")
    
    meeting = upsert_meeting(session, dated_meeting_id, date)
    if not meeting:
        print(f"❌ upsert_meeting failed for meeting_id={dated_meeting_id}")
        return None

    print(
        f"✅ Meeting record ready "
        f"→ db_pk={meeting.id} | meeting_code={meeting.meeting_id}"
    )

    # NEW: normalize possible one-or-many inputs
    summary_items = _dedupe_and_sort_file_payloads(summary_json)
    cat_items = _dedupe_and_sort_file_payloads(captions_and_transcripts)
    transcript_items = _dedupe_and_sort_file_payloads(transcript_json)
    caption_items = _dedupe_and_sort_file_payloads(captions_json)

    for path, raw in summary_items:
        if raw:
            print(f"🧠 Migrating summary for meeting {meeting.id}")
            migrate_summary(session, meeting, raw)
            if path:
                migrate_file_record(session, meeting, path, FileTypeEnum.summary)

    for path, raw in cat_items:
        if raw:
            print(f"📝 Migrating captions_and_transcripts for meeting {meeting.id}")
            migrate_captions_and_transcripts(session, meeting, raw)
            if path:
                # catalog as transcript inventory, since this combined file carries transcript/caption content
                migrate_file_record(session, meeting, path, FileTypeEnum.transcript)

    for path, raw in transcript_items:
        if raw:
            print(f"📜 Migrating transcript_json for meeting {meeting.id}")
            migrate_transcript(session, meeting, raw)
            if path:
                migrate_file_record(session, meeting, path, FileTypeEnum.transcript)

    for path, raw in caption_items:
        if raw is not None:
            print(f"💬 Migrating captions_json for meeting {meeting.id}")
            migrate_captions(session, meeting, raw)
            if path:
                migrate_file_record(session, meeting, path, FileTypeEnum.captions)

    for path, ftype in (media_files or []):
        print(f"🎥 Migrating media file for meeting {meeting.id} → {path} ({ftype})")
        migrate_media_file(session, meeting, path, ftype)

    print(f"🏁 Finished migrate_meeting_folder → meeting {dated_meeting_id}")
    return meeting
