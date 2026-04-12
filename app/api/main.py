"""
ChronoFlow API — Main entry point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.api.routes import media_transcription, meetings, pipeline, analytics, notifications
from app.api.core.config import settings
from app.api.core.logging import configure_logging
from app.api.core.db import create_tables

# Models must be imported before create_tables() so SQLModel
# metadata knows about them — order matters here
from app.api.models.model import (
    User, Meeting, Caption, TranscriptTurn,
    Summary, Job, ParticipantScore, MediaFile
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — create tables if they don't exist yet
    create_tables()
    yield
    # Shutdown — nothing to clean up


app = FastAPI(
    title="ChronoFlow API",
    description="Meeting intelligence pipeline — organize, transcribe, summarize, analyze.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(meetings.router,  prefix="/api/meetings",  tags=["Meetings"])
app.include_router(pipeline.router,  prefix="/api/pipeline",  tags=["Pipeline"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(media_transcription.router, prefix="/api/media-transcription", tags=["Media Transcription"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])

# Serve static dashboard
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(os.path.join(static_dir, "index.html"))

