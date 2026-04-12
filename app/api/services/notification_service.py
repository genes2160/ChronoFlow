from sqlmodel import select

from app.api.core.db import get_session
from app.api.models.model import Notification, NotificationType, NotificationStatus


def create_notification(
    *,
    type: NotificationType,
    status: NotificationStatus,
    title: str,
    message: str,
    meeting_id: int | None = None,
    transcription_job_id: int | None = None,
) -> Notification:
    print(
        f"🔔 [NOTIFY] create -> type={type} status={status} "
        f"meeting_id={meeting_id} transcription_job_id={transcription_job_id}"
    )

    with get_session() as session:
        row = Notification(
            type=type,
            status=status,
            title=title,
            message=message,
            meeting_id=meeting_id,
            transcription_job_id=transcription_job_id,
            is_read=False,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def list_notifications(limit: int = 20, unread_only: bool = False) -> list[Notification]:
    print(f"🔔 [NOTIFY] list -> limit={limit} unread_only={unread_only}")

    with get_session() as session:
        stmt = select(Notification).order_by(Notification.created_at.desc()).limit(limit)

        if unread_only:
            stmt = (
                select(Notification)
                .where(Notification.is_read == False)  # noqa: E712
                .order_by(Notification.created_at.desc())
                .limit(limit)
            )

        rows = session.exec(stmt).all()
        print(f"🔔 [NOTIFY] fetched -> count={len(rows)}")
        return rows

def mark_all_notifications_read() -> int:
    print("🔔 [NOTIFY] mark all read")

    with get_session() as session:
        rows = session.exec(
            select(Notification).where(Notification.is_read == False)  # noqa: E712
        ).all()

        count = 0
        for row in rows:
            row.is_read = True
            session.add(row)
            count += 1

        session.commit()
        print(f"🔔 [NOTIFY] mark all read complete -> count={count}")
        return count
    
def mark_notification_read(notification_id: int) -> Notification:
    print(f"🔔 [NOTIFY] mark read -> id={notification_id}")

    with get_session() as session:
        row = session.get(Notification, notification_id)
        if not row:
            raise ValueError(f"Notification not found: {notification_id}")

        row.is_read = True
        session.add(row)
        session.commit()
        session.refresh(row)
        return row