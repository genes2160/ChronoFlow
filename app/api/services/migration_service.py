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
    r'^[a-z]{3}-[a-z]{4}-[a-z]{3}$'   # hrp-axdm-gqm
    r'|^Meet[_–-].+'                    # Meet_Team_Sync
    r'|^mem-[a-f0-9]{8}$'              # mem-0bb62959 (memory files)
    r'|^ts-[a-f0-9]{8}$'               # ts-a3f9b2c1 (timestamp files)
    r'|^unk-[a-f0-9]{8}$'              # unk-xxxxxxxx (unknown fallback)
)


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
    # Guard: any turns already exist → fully migrated, skip
    if session.exec(
        select(TranscriptTurn).where(TranscriptTurn.meeting_id == meeting.id)
    ).first():
        return

    # handle plain list OR {"transcripts": [...]} shape
    if isinstance(raw, list):
        turns_raw = raw
    elif isinstance(raw, dict):
        turns_raw = raw.get("transcripts") or raw.get("transcript") or []
    else:
        return

    # Collect existing turn_ids to guard against partial inserts
    existing_turn_ids = set(
        session.exec(
            select(TranscriptTurn.turn_id).where(
                TranscriptTurn.meeting_id == meeting.id
            )
        ).all()
    )

    turns = [
        TranscriptTurn(
            meeting_id=meeting.id,
            turn_id=t.get("id", i),
            speaker=t.get("speaker") if t.get("speaker") != "Unknown" else None,
            text=t.get("text", ""),
            timestamp=t.get("timestamp"),
            relative_time=t.get("relativeTime"),
            confidence=t.get("confidence"),
            word_count=t.get("wordCount"),
        )
        for i, t in enumerate(turns_raw)
        if isinstance(t, dict)
        and t.get("text", "").strip()
        and t.get("id", i) not in existing_turn_ids  # skip already-inserted turns
    ]

    if turns:
        session.bulk_save_objects(turns)

    meeting.has_transcript = True
    session.add(meeting)


# ── 4. Captions ───────────────────────────────────────────────────────────

def migrate_captions(session: Session, meeting: Meeting, raw: list | dict) -> None:
    # Guard: any captions already exist → fully migrated, skip
    if session.exec(
        select(Caption).where(Caption.meeting_id == meeting.id)
    ).first():
        return

    items: list = raw if isinstance(raw, list) else (
        raw.get("captions") or raw.get("transcript") or []
    )

    captions = [
        Caption(
            meeting_id=meeting.id,
            speaker=c.get("speaker") if c.get("speaker") != "Unknown" else None,
            text=c["text"],
            ts=c.get("ts"),
        )
        for c in items
        if isinstance(c, dict) and c.get("text", "").strip()
    ]

    if captions:
        session.bulk_save_objects(captions)

    meeting.has_captions = True
    session.add(meeting)


# ── 5. Captions and transcripts ───────────────────────────────────────────────────────────
def migrate_captions_and_transcripts(session: Session, meeting: Meeting, raw: dict) -> None:
    try:
        print(f"▶ Processing meeting {meeting.id}")

        # Skip if already migrated
        has_turns = session.exec(
            select(TranscriptTurn.id).where(TranscriptTurn.meeting_id == meeting.id)
        ).first()

        has_captions = session.exec(
            select(Caption.id).where(Caption.meeting_id == meeting.id)
        ).first()

        if has_turns and has_captions:
            print(f"⏭ Skipping meeting {meeting.id} (already migrated)")
            return

        # ADD THIS LINE HERE
        print(f"📝 Updating meeting metadata {meeting.id}")
        update_meeting_from_raw(meeting, raw)
        
        
        captions_data = raw.get("captions", [])
        transcript_data = raw.get("transcripts", {}).get("transcripts", [])

        print(f"📥 Raw transcript count: {len(transcript_data)}")
        print(f"📥 Raw captions count: {len(captions_data)}")

        # Existing turn IDs (protect against partial insert)
        existing_turn_ids = set(
            session.exec(
                select(TranscriptTurn.turn_id).where(
                    TranscriptTurn.meeting_id == meeting.id
                )
            ).all()
        )

        print(f"🛡 Existing turn IDs: {len(existing_turn_ids)}")

        # ── Build Transcript Turns ─────────────────────────────
        turns = []
        for i, t in enumerate(transcript_data):
            try:
                if not isinstance(t, dict):
                    print(f"⚠️ Skipping non-dict transcript at index {i}")
                    continue

                text = clean_text(t.get("text"))
                if not text:
                    print(f"⚠️ Empty text at transcript index {i}")
                    continue

                turn_id = t.get("id", i)
                if turn_id in existing_turn_ids:
                    print(f"⏭ Skipping existing turn_id {turn_id}")
                    continue

                turns.append(
                    TranscriptTurn(
                        meeting_id=meeting.id,
                        turn_id=turn_id,
                        speaker=clean_speaker(t.get("speaker")),
                        text=text,
                        timestamp=t.get("timestamp"),
                        relative_time=t.get("relativeTime"),
                        confidence=t.get("confidence"),
                        word_count=t.get("wordCount"),
                    )
                )
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

                text = clean_text(c.get("text"))
                if not text:
                    print(f"⚠️ Empty caption text at index {i}")
                    continue

                captions.append(
                    Caption(
                        meeting_id=meeting.id,
                        speaker=clean_speaker(c.get("speaker")),
                        text=text,
                        ts=c.get("ts"),
                    )
                )
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
    # Guard: file record already exists
    if session.exec(
        select(MediaFile).where(
            MediaFile.meeting_id == meeting.id,
            MediaFile.filename == filepath.name,
        )
    ).first():
        return  # ← already exists, nothing to do

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
    filepath: Path,
    date: str,
) -> Meeting | None:
    """
    Handles meet-memory-*.json files.
    Creates a meeting row + captions from user/content shape.
    """
    meeting_id = _generate_mem_meeting_id(filepath.name)

    # Guard: meeting already exists
    existing = session.exec(
        select(Meeting).where(Meeting.meeting_id == meeting_id)
    ).first()

    if existing:
        meeting = existing
    else:
        meeting = Meeting(
            meeting_id=meeting_id,
            date=date,
            duration_minutes=10,
            has_captions=False,
        )
        session.add(meeting)
        session.flush()

    # Guard: captions already migrated
    if session.exec(
        select(Caption).where(Caption.meeting_id == meeting.id)
    ).first():
        return meeting  # ← already exists, nothing to do

    raw = _load_json_file(filepath)
    if not raw:
        return None

    items = raw if isinstance(raw, list) else raw.get("transcript", [])

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

    if captions:
        session.bulk_save_objects(captions)
        meeting.has_captions = True
        session.add(meeting)

    return meeting


# ── Orchestrator ──────────────────────────────────────────────────────────

def migrate_meeting_folder(
    session: Session,
    meeting_id: str,
    date: str,
    captions_and_transcripts: dict | None = None,
    summary_json: dict | None = None,
    transcript_json: dict | None = None,
    captions_json: list | dict | None = None,
    media_files: list[tuple[Path, FileTypeEnum]] | None = None,
) -> Meeting | None:
    print(f"📁 migrate_meeting_folder → meeting_id={meeting_id}, date={date}")

    meeting = upsert_meeting(session, meeting_id, date)
    if not meeting:
        print(f"❌ upsert_meeting failed for meeting_id={meeting_id}")
        return None

    print(f"✅ Meeting record ready → DB id={meeting.id}")

    if summary_json:
        print(f"🧠 Migrating summary for meeting {meeting.id}")
        migrate_summary(session, meeting, summary_json)

    if captions_and_transcripts:
        print(f"📝 Migrating captions_and_transcripts for meeting {meeting.id}")
        migrate_captions_and_transcripts(session, meeting, captions_and_transcripts)

    if transcript_json:
        print(f"📜 Migrating transcript_json for meeting {meeting.id}")
        migrate_transcript(session, meeting, transcript_json)

    if captions_json is not None:
        print(f"💬 Migrating captions_json for meeting {meeting.id}")
        migrate_captions(session, meeting, captions_json)

    for path, ftype in (media_files or []):
        print(f"🎥 Migrating media file for meeting {meeting.id} → {path} ({ftype})")
        migrate_media_file(session, meeting, path, ftype)

    print(f"🏁 Finished migrate_meeting_folder → meeting {meeting.id}")
    return meeting
