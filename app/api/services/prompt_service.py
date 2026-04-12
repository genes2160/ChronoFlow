from sqlmodel import select

from app.api.core.db import get_session
from app.api.models.model import Prompt
from app.api.schema.schemas import (
    PromptCreateRequest,
    PromptUpdateRequest,
)


def list_prompts() -> list[Prompt]:
    with get_session() as session:
        return session.exec(
            select(Prompt).order_by(Prompt.updated_at.desc())
        ).all()


def get_prompt(prompt_id: int) -> Prompt | None:
    with get_session() as session:
        return session.get(Prompt, prompt_id)


def create_prompt(req: PromptCreateRequest) -> Prompt:
    with get_session() as session:
        if req.is_active:
            rows = session.exec(select(Prompt).where(Prompt.is_active == True)).all()  # noqa: E712
            for row in rows:
                row.is_active = False
                session.add(row)

        row = Prompt(
            name=req.name,
            version=req.version,
            text=req.text,
            is_active=req.is_active,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def update_prompt(prompt_id: int, req: PromptUpdateRequest) -> Prompt:
    with get_session() as session:
        row = session.get(Prompt, prompt_id)
        if not row:
            raise ValueError(f"Prompt not found: {prompt_id}")

        if req.is_active is True:
            active_rows = session.exec(
                select(Prompt).where(Prompt.is_active == True, Prompt.id != prompt_id)  # noqa: E712
            ).all()
            for active in active_rows:
                active.is_active = False
                session.add(active)

        if req.name is not None:
            row.name = req.name
        if req.version is not None:
            row.version = req.version
        if req.text is not None:
            row.text = req.text
        if req.is_active is not None:
            row.is_active = req.is_active

        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def activate_prompt(prompt_id: int) -> Prompt:
    with get_session() as session:
        row = session.get(Prompt, prompt_id)
        if not row:
            raise ValueError(f"Prompt not found: {prompt_id}")

        active_rows = session.exec(
            select(Prompt).where(Prompt.is_active == True, Prompt.id != prompt_id)  # noqa: E712
        ).all()
        for active in active_rows:
            active.is_active = False
            session.add(active)

        row.is_active = True
        session.add(row)
        session.commit()
        session.refresh(row)
        return row