import json

from sqlmodel import select

from app.api.core.db import get_session
from app.api.models.model import (
    Meeting,
    Prompt,
    Caption,
    TranscriptTurn,
    MediaTranscriptionJob,
    MediaTranscriptionStatus,
)
from app.api.schema.schemas import (
    SummaryPayloadSimulationRequest,
    SummaryPayloadSimulationResponse,
    SummaryPayloadVariantResponse,
)
from app.llm.base import estimate_tokens


def _load_meeting_bundle(
    meeting_id: str,
    prompt_name: str,
    prompt_version: str,
):
    with get_session() as session:
        meeting = session.exec(
            select(Meeting).where(Meeting.meeting_id == meeting_id)
        ).first()

        if not meeting:
            raise ValueError(f"Meeting not found: {meeting_id}")

        prompt = session.exec(
            select(Prompt).where(
                Prompt.name == prompt_name,
                Prompt.version == prompt_version,
                Prompt.is_active == True,  # noqa: E712
            )
        ).first()

        if not prompt:
            raise ValueError(
                f"Active prompt not found: {prompt_name} v{prompt_version}"
            )

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
            # "raw_response": mt.raw_response,
            "completed_at": mt.completed_at.isoformat() if mt.completed_at else None,
        }
        for mt in media_transcriptions
        if mt.transcript_text
    ]

    return {
        "meeting": meeting,
        "prompt": prompt,
        "transcripts": transcript_payload,
        "captions": caption_payload,
        "media_transcriptions": media_payload,
    }


def _build_variants(bundle: dict):
    transcripts = bundle["transcripts"]
    captions = bundle["captions"]
    media_transcriptions = bundle["media_transcriptions"]

    return [
        {
            "key": "prompt_only",
            "label": "Prompt only",
            "data": {},
            "included_sources": [],
        },
        {
            "key": "transcript_prompt",
            "label": "Transcript + prompt",
            "data": {"transcripts": transcripts},
            "included_sources": ["transcripts"],
        },
        {
            "key": "captions_prompt",
            "label": "Captions + prompt",
            "data": {"captions": captions},
            "included_sources": ["captions"],
        },
        {
            "key": "media_prompt",
            "label": "Media transcription + prompt",
            "data": {"media_transcriptions": media_transcriptions},
            "included_sources": ["media_transcriptions"],
        },
        {
            "key": "all_sources_prompt",
            "label": "Transcript + captions + media transcription + prompt",
            "data": {
                "transcripts": transcripts,
                "captions": captions,
                "media_transcriptions": media_transcriptions,
            },
            "included_sources": ["transcripts", "captions", "media_transcriptions"],
        },
    ]


def simulate_summary_payload(
    req: SummaryPayloadSimulationRequest,
) -> SummaryPayloadSimulationResponse:
    bundle = _load_meeting_bundle(
        meeting_id=req.meeting_id,
        prompt_name=req.prompt_name,
        prompt_version=req.prompt_version,
    )

    prompt = bundle["prompt"]
    prompt_text = prompt.text

    prompt_only_chars = len(prompt_text)
    prompt_only_tokens = estimate_tokens(prompt_text)

    variants = _build_variants(bundle)

    all_variant = next(v for v in variants if v["key"] == "all_sources_prompt")
    all_payload_json = json.dumps(all_variant["data"], ensure_ascii=False, indent=2)
    all_filled_prompt = prompt_text.replace("<transcript>", all_payload_json)
    all_final_tokens = estimate_tokens(all_filled_prompt)

    results: list[SummaryPayloadVariantResponse] = []

    counts = {
        "transcript_items": len(bundle["transcripts"]),
        "caption_items": len(bundle["captions"]),
        "media_transcription_items": len(bundle["media_transcriptions"]),
    }

    for variant in variants:
        payload_json = json.dumps(variant["data"], ensure_ascii=False, indent=2)
        filled_prompt = prompt_text.replace("[PASTE TRANSCRIPT HERE]", payload_json)

        payload_chars = len(payload_json)
        payload_tokens = estimate_tokens(payload_json)
        final_chars = len(filled_prompt)
        final_tokens = estimate_tokens(filled_prompt)

        reduction = None
        if all_final_tokens > 0:
            reduction = round(
                ((all_final_tokens - final_tokens) / all_final_tokens) * 100,
                2,
            )

        results.append(
            SummaryPayloadVariantResponse(
                key=variant["key"],
                label=variant["label"],
                included_sources=variant["included_sources"],
                counts=counts,
                payload_chars=payload_chars,
                payload_tokens=payload_tokens,
                prompt_chars=prompt_only_chars,
                prompt_tokens=prompt_only_tokens,
                final_chars=final_chars,
                final_tokens=final_tokens,
                reduction_vs_all_percent=reduction,
                preview=filled_prompt[:req.preview_chars],
            )
        )

    return SummaryPayloadSimulationResponse(
        meeting_id=req.meeting_id,
        prompt_name=req.prompt_name,
        prompt_version=req.prompt_version,
        variants=results,
    )