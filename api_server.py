"""
Run ChronoFlow API:
    python api_server.py
"""
import uvicorn
from app.api.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,   # already int from pydantic
        reload=settings.DEBUG,
        reload_dirs=["app"],   # ← watches the app directory
        log_level="info",
        
    )