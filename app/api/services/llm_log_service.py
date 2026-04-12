import json

from sqlmodel import select

from app.api.core.db import get_session
from app.api.models.model import (
    LLMRequestLog,
    Prompt,
    Meeting,
    Caption,
    TranscriptTurn,
    MediaTranscriptionJob,
    MediaTranscriptionStatus,
)
from app.llm.base import estimate_tokens


def list_llm_logs(limit: int = 50) -> list[LLMRequestLog]:
    with get_session() as session:
        return session.exec(
            select(LLMRequestLog)
            .order_by(LLMRequestLog.created_at.desc())
            .limit(limit)
        ).all()


def get_llm_log(log_id: int) -> LLMRequestLog | None:
    with get_session() as session:
        return session.get(LLMRequestLog, log_id)


def _build_live_simulation(log_row: LLMRequestLog) -> dict:
    with get_session() as session:
        prompt = session.get(Prompt, log_row.prompt_id)
        if not prompt:
            raise ValueError(f"Prompt not found for log: {log_row.prompt_id}")

        meeting = session.exec(
            select(Meeting).where(Meeting.meeting_id == log_row.meeting_id)
        ).first()
        if not meeting:
            raise ValueError(f"Meeting not found for log: {log_row.meeting_id}")

        captions = session.exec(
            select(Caption)
            .where(Caption.meeting_id == meeting.id)
            .order_by(Caption.ts)
        ).all()

        turns = session.exec(
            select(TranscriptTurn)
            .where(TranscriptTurn.meeting_id == meeting.id)
            .order_by(TranscriptTurn.turn_id)
        ).all()

        media_transcriptions = session.exec(
            select(MediaTranscriptionJob)
            .where(
                MediaTranscriptionJob.meeting_id == meeting.id,
                MediaTranscriptionJob.status == MediaTranscriptionStatus.completed,
            )
            .order_by(MediaTranscriptionJob.completed_at.desc())
        ).all()

    prompt_text = prompt.text

    transcript_payload = [
        {
            "id": t.turn_id,
            "speaker": t.speaker,
            "text": t.text,
            "timestamp": t.timestamp,
            "relativeTime": t.relative_time,
            "confidence": t.confidence,
            "wordCount": t.word_count,
        }
        for t in turns
    ]

    caption_payload = [
        {
            "speaker": c.speaker,
            "text": c.text,
            "ts": c.ts,
        }
        for c in captions
    ]

    media_payload = [
        {
            "id": mt.id,
            "source_filename": mt.source_filename,
            "source_file_type": mt.source_file_type,
            "provider": mt.provider,
            "transcript_text": mt.transcript_text,
            "raw_response": mt.raw_response,
            "completed_at": mt.completed_at.isoformat() if mt.completed_at else None,
        }
        for mt in media_transcriptions
        if mt.transcript_text
    ]

    variants = [
        {
            "key": "prompt_only",
            "label": "Prompt only",
            "included_sources": [],
            "data": {},
        },
        {
            "key": "transcript_prompt",
            "label": "Transcript + prompt",
            "included_sources": ["transcripts"],
            "data": {"transcripts": transcript_payload},
        },
        {
            "key": "captions_prompt",
            "label": "Captions + prompt",
            "included_sources": ["captions"],
            "data": {"captions": caption_payload},
        },
        {
            "key": "media_prompt",
            "label": "Media transcription + prompt",
            "included_sources": ["media_transcriptions"],
            "data": {"media_transcriptions": media_payload},
        },
        {
            "key": "all_sources_prompt",
            "label": "Transcript + captions + media transcription + prompt",
            "included_sources": ["transcripts", "captions", "media_transcriptions"],
            "data": {
                "transcripts": transcript_payload,
                "captions": caption_payload,
                "media_transcriptions": media_payload,
            },
        },
    ]

    all_variant = next(v for v in variants if v["key"] == "all_sources_prompt")
    all_payload_json = json.dumps(all_variant["data"], ensure_ascii=False, indent=2)
    all_filled_prompt = prompt_text.replace("<transcript>", all_payload_json)
    all_final_tokens = estimate_tokens(all_filled_prompt)

    out = []
    for v in variants:
        payload_json = json.dumps(v["data"], ensure_ascii=False, indent=2)
        filled_prompt = prompt_text.replace("<transcript>", payload_json)

        final_tokens = estimate_tokens(filled_prompt)
        reduction = None
        if all_final_tokens > 0:
            reduction = round(
                ((all_final_tokens - final_tokens) / all_final_tokens) * 100,
                2,
            )

        out.append(
            {
                "key": v["key"],
                "label": v["label"],
                "included_sources": v["included_sources"],
                "payload_chars": len(payload_json),
                "payload_tokens": estimate_tokens(payload_json),
                "final_chars": len(filled_prompt),
                "final_tokens": final_tokens,
                "reduction_vs_all_percent": reduction,
                "preview": filled_prompt[:1200],
            }
        )

    return {
        "prompt": {
            "id": prompt.id,
            "name": prompt.name,
            "version": prompt.version,
            "is_active": prompt.is_active,
        },
        "counts": {
            "transcript_items": len(transcript_payload),
            "caption_items": len(caption_payload),
            "media_transcription_items": len(media_payload),
        },
        "variants": out,
    }


def get_llm_log_detail(log_id: int) -> dict | None:
    row = get_llm_log(log_id)
    if not row:
        return None

    return {
        "log": row,
        "simulation": _build_live_simulation(row),
    }