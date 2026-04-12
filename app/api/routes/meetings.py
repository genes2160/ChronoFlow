"""
ChronoFlow — /api/meetings routes
"""

from app.api.core.db import get_session
from app.api.services.reconciliation_service import fix_missing_files_in_db, reconcile_organized_files_vs_db
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from fastapi.responses import FileResponse
from app.api.schema.schemas import FileReconciliationResponse, MeetingsListResponse, MeetingDetailResponse, RawFilesResponse
from app.api.services import meetings_service
from app.api.services  import db_meetings_service
from app.api.services  import db_participant_stats_service
from app.api.core.config import settings

router = APIRouter()


@router.get("/", response_model=MeetingsListResponse)
def list_meetings(
    date: Optional[str] = None,
    has_summary: Optional[bool] = None,
    search: Optional[str] = None,

    # ✅ pagination
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),

    # ✅ sorting
    sort_by: Optional[str] = "date",
    sort_order: Optional[str] = "desc",
):
    # data = meetings_service.list_meetings()
    with get_session() as session:
        return db_meetings_service.list_meetings(
            session=session,
            date=date,
            has_summary=has_summary,
            search=search,
            page=page,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )

@router.get("/raw", response_model=RawFilesResponse, summary="List unprocessed raw files")
def list_raw_files():
    return  db_meetings_service.get_raw_files()
    # return meetings_service.get_raw_files()

@router.post(
    "/reconcile/files/fix",
    summary="Fix missing organized files in DB inventory and content",
)
def fix_reconciled_files(
    target_date: str | None = Query(default=None, description="Optional date folder like 2026-04-08"),
):
    return fix_missing_files_in_db(target_date=target_date)

@router.get(
    "/reconcile/files",
    response_model=FileReconciliationResponse,
    summary="Compare organized folder files vs DB file inventory",
)
def reconcile_files(
    target_date: str | None = Query(default=None, description="Optional date folder like 2026-03-20")
):
    return reconcile_organized_files_vs_db(target_date=target_date)

@router.get("/{date}/{meeting_id}/captions", summary="Get captions for a meeting")
def get_captions(date: str, meeting_id: str):
    captions =  db_meetings_service.get_captions_and_transcripts(meeting_id, date)
    # captions = meetings_service.get_captions(meeting_id, date)
    if captions is None:
        raise HTTPException(status_code=404, detail="No captions file found for this meeting")
    # return {"captions": captions}
    return captions


@router.get("/{date}/{meeting_id}", response_model=MeetingDetailResponse, summary="Get meeting detail")
def get_meeting(date: str, meeting_id: str):
    meeting =  db_meetings_service.get_meeting_detail(meeting_id, date)
    # meeting = meetings_service.get_meeting_detail(meeting_id, date)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingDetailResponse(meeting=meeting)


@router.get("/file/{date}/{filename}")
def serve_file(date: str, filename: str):
    path = settings.ORGANIZED_DATA_DIR / date / filename
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="video/webm")

@router.get("/migration-run")
def run_migration():
    from app.api.services.migration_runner import run_backfill
    run_backfill()
    return {
        "status": "Done"
    }
    
@router.get("/stats")
def participants_stats():
    return db_participant_stats_service.get_participant_aggregates()
