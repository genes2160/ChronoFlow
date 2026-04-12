from fastapi import APIRouter, HTTPException, Query

from app.api.schema.schemas import NotificationListResponse, NotificationResponse
from app.api.services.notification_service import list_notifications, mark_all_notifications_read, mark_notification_read

router = APIRouter()


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List app notifications",
)
def get_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
):
    rows = list_notifications(limit=limit, unread_only=unread_only)
    return NotificationListResponse(
        items=[
            NotificationResponse(
                id=row.id,
                type=row.type,
                status=row.status,
                title=row.title,
                message=row.message,
                meeting_id=row.meeting_id,
                transcription_job_id=row.transcription_job_id,
                is_read=row.is_read,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
)
def read_notification(notification_id: int):
    try:
        row = mark_notification_read(notification_id)
        return NotificationResponse(
            id=row.id,
            type=row.type,
            status=row.status,
            title=row.title,
            message=row.message,
            meeting_id=row.meeting_id,
            transcription_job_id=row.transcription_job_id,
            is_read=row.is_read,
            created_at=row.created_at,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post(
    "/read-all",
    summary="Mark all notifications as read",
)
def read_all_notifications():
    try:
        count = mark_all_notifications_read()
        return {"ok": True, "count": count}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))