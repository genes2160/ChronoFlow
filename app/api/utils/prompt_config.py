import hashlib
import json
from app.api.models.model import LLMRequestLog, Prompt
from sqlmodel import Session, select

def get_data_hash(data: dict | str) -> str:
    s = str(data) if isinstance(data, dict) else data
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_or_create_prompt(session: Session, name: str, text: str, version: str = "1.0") -> Prompt:
    existing = session.exec(
        select(Prompt).where(Prompt.name == name, Prompt.version == version)
    ).first()
    if existing:
        return existing
    prompt = Prompt(name=name, version=version, text=text)
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt

def log_llm_request(
    session: Session,
    prompt_id: int,
    meeting_id: str,
    provider: str,
    model: str,
    data: dict | str,
    response: str,
    duration_sec: float,
):
    data_hash = get_data_hash(data)

    existing = session.exec(
        select(LLMRequestLog).where(
            LLMRequestLog.prompt_id == prompt_id,
            LLMRequestLog.meeting_id == meeting_id,
            LLMRequestLog.provider == provider,
            LLMRequestLog.model == model,
            LLMRequestLog.data_hash == data_hash
        )
    ).first()

    if existing:
        # Already processed → do nothing
        return existing

    log = LLMRequestLog(
        prompt_id=prompt_id,
        meeting_id=meeting_id,
        provider=provider,
        model=model,
        data_hash=data_hash,
        response=response,
        duration_sec=duration_sec
    )
    session.add(log)
    session.commit()
    return log


def get_data_hash(data: dict) -> str:
    """Deterministic hash for deduplication"""
    import hashlib
    data_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data_bytes).hexdigest()
