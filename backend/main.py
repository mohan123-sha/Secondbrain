import os
import sys
import subprocess
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Ensure backend imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from search import generate_rag_response_stream
from db import get_collection

load_dotenv()

app = FastAPI(
    title="Esperia MemoryOS API",
    description="Backend services for Esperia AI Organizational Memory and Meeting Intelligence.",
    version="1.0.0"
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/status")
def get_status():
    """Retrieve system health and database statistics."""
    try:
        collection = get_collection()
        count = collection.count()
        return {
            "status": "online",
            "database": "connected",
            "total_chunks": count,
            "groq_configured": bool(os.getenv("GROQ_API_KEY")),
            "zoom_configured": bool(os.getenv("ZOOM_CLIENT_ID")),
            "box_configured": bool(os.getenv("BOX_DEVELOPER_TOKEN"))
        }
    except Exception as e:
        return {
            "status": "error",
            "database": "failed_to_connect",
            "error": str(e)
        }

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    RAG Chat endpoint. Accepts a JSON body with a 'message' string,
    and returns a Server-Sent Events (SSE) stream of the synthesized answer.
    """
    body = await request.json()
    message = body.get("message", "").strip()
    
    if not message:
        return {"error": "Message content cannot be empty."}
        
    return StreamingResponse(
        generate_rag_response_stream(message),
        media_type="text/event-stream"
    )

@app.post("/api/ingest")
def trigger_ingestion():
    """
    Triggers the end-to-end ingestion pipeline manually.
    Calls pipeline.py as a subprocess so that it executes in isolation.
    """
    print("[API Trigger] Manual Ingestion Triggered!")
    pipeline_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pipeline.py")
    
    try:
        # Run pipeline using the virtual environment's python if it exists, otherwise fallback
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        venv_python = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
        
        python_cmd = venv_python if os.path.exists(venv_python) else "py"
        
        result = subprocess.run(
            [python_cmd, pipeline_path],
            capture_output=True,
            text=True,
            cwd=base_dir
        )
        
        if result.returncode == 0:
            return {
                "status": "success",
                "message": "Ingestion pipeline completed successfully.",
                "output": result.stdout
            }
        else:
            return {
                "status": "failed",
                "message": f"Pipeline failed with exit code: {result.returncode}",
                "error": result.stderr,
                "output": result.stdout
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"An error occurred executing pipeline script: {str(e)}"
        }

# Mount Frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
os.makedirs(frontend_dir, exist_ok=True)
os.makedirs(os.path.join(frontend_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(frontend_dir, "js"), exist_ok=True)

# Mount the static files router
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Start on port 8000
    print("[API Server] Starting FastAPI on http://localhost:8000...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
