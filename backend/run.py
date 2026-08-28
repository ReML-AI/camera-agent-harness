"""Run the FastAPI server"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        # This auxiliary prototype has no authentication. Keep it local-only.
        host="127.0.0.1",
        port=8001,
        reload=False,
    )
