"""FastAPI main application"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
from pathlib import Path

from .database import init_db
from .routers._validation import require_file_component, require_session_id
from .routers import sessions, feedback, interactions, videos, reports, labeling, students, interaction_analytics, debrief_plans, review_clips

# Initialize FastAPI app
app = FastAPI(title="Clinical Simulation Review System")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Include routers
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(interactions.router, prefix="/api/interactions", tags=["interactions"])
app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(labeling.router, prefix="/api/labeling", tags=["labeling"])
app.include_router(students.router, prefix="/api/students", tags=["students"])
app.include_router(interaction_analytics.router, prefix="/api/interactions-analytics", tags=["interaction-analytics"])
app.include_router(debrief_plans.router, prefix="/api/debrief-plans", tags=["debrief-plans"])
app.include_router(review_clips.router, prefix="/api/review-clips", tags=["review-clips"])


# Serve frontend static files (CSS, JS, assets)
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend-assets")


@app.get("/")
def read_root():
    """Serve frontend index.html at root."""
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Clinical Simulation Review System API", "status": "running"}


@app.get("/api/health")
def health_check():
    return {"status": "healthy"}


@app.get("/api/thumbnails/{filename}")
async def get_thumbnail(filename: str):
    """Serve person thumbnails"""
    filename = require_file_component(filename)
    thumbnail_path = Path(__file__).parent.parent.parent / "data" / "processed" / "thumbnails" / filename
    if thumbnail_path.exists():
        return FileResponse(thumbnail_path)
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.get("/api/report-assets/{session_id}/{asset_type}/{filename}")
async def get_report_asset(session_id: str, asset_type: str, filename: str):
    """Serve generated report assets (speaker portraits, annotated moment frames)."""
    session_id = require_session_id(session_id)
    if asset_type not in ("speakers", "moments"):
        raise HTTPException(status_code=400, detail="Invalid asset type")
    filename = require_file_component(filename)
    asset_path = Path(__file__).parent.parent.parent / "data" / "processed" / "report_assets" / session_id / asset_type / filename
    if asset_path.exists():
        return FileResponse(asset_path)
    raise HTTPException(status_code=404, detail="Asset not found")


@app.get("/api/report-assets/{session_id}/manifest.json")
async def get_report_manifest(session_id: str):
    """Serve report assets manifest."""
    session_id = require_session_id(session_id)
    manifest_path = Path(__file__).parent.parent.parent / "data" / "processed" / "report_assets" / session_id / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="Manifest not found")


# SPA catch-all: serve index.html for any non-API route (must be last)
@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    """Catch-all for SPA client-side routing."""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")
