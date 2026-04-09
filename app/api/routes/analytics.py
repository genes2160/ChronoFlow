"""
ChronoFlow — /api/analytics routes
"""

from fastapi import APIRouter
from app.api.schema.schemas import AnalyticsOverview
from app.api.services import analytics_service
from app.api.services import db_analytics_service

router = APIRouter()


@router.get("/overview", response_model=AnalyticsOverview, summary="Global stats overview")
def get_overview():
    """
    Returns aggregate stats across all organized meetings:
    totals, pending files, effectiveness scores, top participants, etc.
    """
    return db_analytics_service.get_overview()
    # return analytics_service.get_overview()
