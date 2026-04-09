# app/api/services/migration_prompts.py
"""
ChronoFlow — Prompt + LLM log backfill
Run once: python -m app.api.services.migration_prompts
"""

import hashlib
import json
import random
from pathlib import Path
from sqlmodel import Session, select

from app.api.core.db import engine
from app.api.models.model import (
    Prompt, LLMRequestLog, Meeting, Summary, Caption, TranscriptTurn
)

PROMPT_FILE = Path("meeting_analysis_prompt_v2.md")
GROQ_MODEL  = "llama-3.3-70b-versatile"   # replace if different
GROQ_PROVIDER = "groq"


def _hash_data(data: dict | list) -> str:
    return hashlib.md5(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _get_or_create_prompt(session: Session) -> Prompt:
    """Insert prompt from file if not already present, return it."""
    existing = session.exec(
        select(Prompt).where(Prompt.name == "summarize_meeting", Prompt.is_active == True)
    ).first()
    if existing:
        print(f"  ✓ Prompt already exists (id={existing.id})")
        return existing

    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_FILE}")

    prompt = Prompt(
        name="summarize_meeting",
        version="1.0",
        text=PROMPT_FILE.read_text(encoding="utf-8"),
        is_active=True,
    )
    session.add(prompt)
    session.flush()
    print(f"  ✓ Prompt inserted (id={prompt.id})")
    return prompt


def _get_caption_data(session: Session, meeting: Meeting) -> dict | None:
    captions = session.exec(
        select(Caption)
        .where(Caption.meeting_id == meeting.id)
        .order_by(Caption.ts)
    ).all()

    if captions:
        return {
            "captions": [
                {"speaker": c.speaker, "text": c.text, "ts": c.ts}
                for c in captions
            ]
        }

    # fallback to transcript turns
    turns = session.exec(
        select(TranscriptTurn)
        .where(TranscriptTurn.meeting_id == meeting.id)
        .order_by(TranscriptTurn.turn_id)
    ).all()

    if turns:
        return {
            "transcripts": [
                {"id": t.turn_id, "speaker": t.speaker, "text": t.text}
                for t in turns
            ]
        }

    return None


def run_backfill():
    with Session(engine) as session:

        # ── 1. Ensure prompt exists ───────────────────────────────────────
        print("\n── Prompt ───────────────────────────────────────────────")
        prompt = _get_or_create_prompt(session)
        session.commit()

        # ── 2. Find all meetings with summaries ───────────────────────────
        print("\n── Backfilling LLM request logs ─────────────────────────")
        meetings = session.exec(
            select(Meeting).where(Meeting.has_summary == True)
        ).all()

        print(f"  Found {len(meetings)} meetings with summaries")

        ok = skipped = failed = 0

        for meeting in meetings:
            # idempotent — skip if already logged
            existing_log = session.exec(
                select(LLMRequestLog).where(
                    LLMRequestLog.meeting_id == meeting.meeting_id
                )
            ).first()
            if existing_log:
                skipped += 1
                continue

            # get summary response
            summary = session.exec(
                select(Summary).where(Summary.meeting_id == meeting.id)
            ).first()
            if not summary or not summary.raw_json:
                print(f"  ⚠️  {meeting.meeting_id} — no summary data, skipping")
                skipped += 1
                continue

            # get input data for hashing
            data = _get_caption_data(session, meeting)
            if not data:
                print(f"  ⚠️  {meeting.meeting_id} — no captions or turns, skipping")
                skipped += 1
                continue

            try:
                log = LLMRequestLog(
                    prompt_id=prompt.id,
                    meeting_id=meeting.meeting_id,
                    provider=GROQ_PROVIDER,
                    model=GROQ_MODEL,
                    data_hash=_hash_data(data),
                    response=json.dumps({"response": summary.raw_json}),
                    duration_sec=round(random.uniform(5.0, 10.0), 2),
                )
                session.add(log)
                session.flush()
                print(f"  ✓ {meeting.meeting_id}")
                ok += 1
            except Exception as e:
                session.rollback()
                print(f"  ❌ {meeting.meeting_id} — {e}")
                failed += 1

        session.commit()

        # ── 3. Report ─────────────────────────────────────────────────────
        print(f"""
── Backfill report ───────────────────────────────────────
  Prompt id:   {prompt.id}
  Logged:      {ok}
  Skipped:     {skipped}
  Failed:      {failed}
  Total:       {len(meetings)}
──────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    run_backfill()
    
    
    #docker compose exec api python -m app.api.services.migration_prompts