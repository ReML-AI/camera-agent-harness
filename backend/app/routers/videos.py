"""Optimized video streaming endpoints with better caching and performance"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pathlib import Path
import os
from datetime import datetime, timedelta

router = APIRouter()

from ._validation import require_session_id

# Cache video metadata to avoid repeated os.stat calls
VIDEO_CACHE = {}


def get_video_metadata(file_path: Path):
    """Get or cache video file metadata"""
    cache_key = str(file_path)

    # Check if file has been modified since last cache
    current_mtime = os.path.getmtime(file_path)

    if cache_key in VIDEO_CACHE:
        cached_data, cached_mtime = VIDEO_CACHE[cache_key]
        if cached_mtime == current_mtime:
            return cached_data

    # Calculate fresh metadata
    file_size = os.path.getsize(file_path)

    # Generate ETag from file size and modification time
    etag = f'"{file_size}-{int(current_mtime)}"'

    metadata = {
        'size': file_size,
        'etag': etag,
        'mtime': current_mtime
    }

    VIDEO_CACHE[cache_key] = (metadata, current_mtime)
    return metadata


def range_requests_response(
    request: Request, file_path: Path, content_type: str = "video/mp4"
):
    """Optimized video streaming with HTTP range request support and caching"""

    metadata = get_video_metadata(file_path)
    file_size = metadata['size']
    etag = metadata['etag']

    # Check If-None-Match header for conditional requests (ETag validation)
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return StreamingResponse(
            iter([]),
            status_code=304,  # Not Modified
            headers={"ETag": etag}
        )

    range_header = request.headers.get("range")

    # Cache videos for 1 year since they don't change
    cache_control = "public, max-age=31536000, immutable"

    # Set expiry date 1 year in the future
    expires = (datetime.now() + timedelta(days=365)).strftime("%a, %d %b %Y %H:%M:%S GMT")

    if range_header:
        # Parse range header
        try:
            byte_range = range_header.strip().split("=")[1]
            start, end = byte_range.split("-")
            start = int(start)
            end = int(end) if end else file_size - 1
            end = min(end, file_size - 1)

            # Validate range
            if start >= file_size or end >= file_size or start > end:
                return StreamingResponse(
                    iter([]),
                    status_code=416,  # Range Not Satisfiable
                    headers={"Content-Range": f"bytes */{file_size}"}
                )

            chunk_size = end - start + 1
        except (ValueError, IndexError):
            # Invalid range header, return full file
            start = 0
            end = file_size - 1
            chunk_size = file_size

        # OPTIMIZED: Use generator for memory-efficient streaming
        def file_chunk_generator():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size

                # Stream in 64KB chunks for better performance
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": content_type,
            "Cache-Control": cache_control,
            "Expires": expires,
            "ETag": etag,
        }

        return StreamingResponse(
            file_chunk_generator(),
            status_code=206,
            headers=headers,
            media_type=content_type
        )
    else:
        # Return full file with streaming
        def file_generator():
            with open(file_path, "rb") as f:
                # Stream in 1MB chunks for full file
                while chunk := f.read(1048576):
                    yield chunk

        headers = {
            "Content-Length": str(file_size),
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Cache-Control": cache_control,
            "Expires": expires,
            "ETag": etag,
        }

        return StreamingResponse(
            file_generator(),
            status_code=200,
            headers=headers,
            media_type=content_type
        )


@router.get("/{session_id}/{camera}")
def stream_video_session(session_id: str, camera: str, request: Request):
    """Stream video for a specific session"""
    session_id = require_session_id(session_id)
    video_files = {"cam1": "cam1.mp4", "cam2": "cam2.mp4", "cam3": "cam3.mp4", "monitor": "monitor.mp4"}
    if camera not in video_files:
        raise HTTPException(status_code=404, detail="Camera not found")
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    sessions_base = (PROJECT_ROOT / "data" / "sessions").resolve()
    video_path = (sessions_base / session_id / "videos" / video_files[camera]).resolve()
    if not str(video_path).startswith(str(sessions_base) + os.sep):
        raise HTTPException(status_code=404, detail="Video file not found")
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return range_requests_response(request, video_path)
