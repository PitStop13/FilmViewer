import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import uuid

from backend.domain_manager import domain_watch_loop, run_check, get_current_domain
from backend.scraper import search_title, get_title_details, extract_iframe_url
from backend.m3u8_parser import parse_master_playlist
from backend.downloader import download_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start domain watcher
    domain_task = asyncio.create_task(domain_watch_loop())
    yield
    # Shutdown: Cancel background tasks
    domain_task.cancel()

app = FastAPI(lifespan=lifespan)

# Setup Config Directory
CONFIG_FILE = "/app/config/settings.json"

class SetupSettings(BaseModel):
    download_path: str
    default_format: str
    default_quality: str
    domain: str | None = None

class DownloadRequest(BaseModel):
    m3u8_url: str
    title: str
    format: str
    quality: str
    download_path: str = "/app/downloads"

@app.get("/api/status")
async def get_status():
    domain = get_current_domain()
    return {"status": "ok", "domain": domain}

@app.post("/api/domain/check")
async def force_domain_check():
    result = run_check(force=True)
    return result

@app.get("/api/search")
async def search(q: str):
    try:
        results = search_title(q)
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/title/{title_id}")
async def title_details(title_id: int):
    try:
        details = get_title_details(title_id)
        return {"data": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream/url")
async def get_stream_url(title_id: int, episode_id: int | None = None):
    try:
        m3u8_url = extract_iframe_url(title_id, episode_id)
        if not m3u8_url:
            raise HTTPException(status_code=404, detail="Could not find stream URL")

        # Parse master playlist to get qualities
        qualities = parse_master_playlist(m3u8_url)
        return {"url": m3u8_url, "qualities": qualities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download")
async def start_download(req: DownloadRequest):
    task_id = str(uuid.uuid4())
    output_dir = req.download_path or "/app/downloads"
    output_path = os.path.join(output_dir, f"{req.title}.{req.format}")

    download_manager.add_task(task_id, req.m3u8_url, output_path, req.format, req.quality)
    return {"task_id": task_id, "status": "started"}

@app.post("/api/download/{task_id}/cancel")
async def cancel_download(task_id: str):
    task = download_manager.get_task(task_id)
    if task:
        task.cancel()
        return {"status": "cancelled"}
    raise HTTPException(status_code=404, detail="Task not found")

@app.post("/api/download/{task_id}/pause")
async def pause_download(task_id: str):
    task = download_manager.get_task(task_id)
    if task and task.process and task.status == "downloading":
        import signal
        task.process.send_signal(signal.SIGSTOP)
        task.status = "paused"
        await download_manager.broadcast_progress()
        return {"status": "paused"}
    raise HTTPException(status_code=404, detail="Task not found or not active")

@app.post("/api/download/{task_id}/resume")
async def resume_download(task_id: str):
    task = download_manager.get_task(task_id)
    if task and task.process and task.status == "paused":
        import signal
        task.process.send_signal(signal.SIGCONT)
        task.status = "downloading"
        await download_manager.broadcast_progress()
        return {"status": "resumed"}
    raise HTTPException(status_code=404, detail="Task not found or not paused")

@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    download_manager.websockets.add(websocket)
    try:
        # Send initial state
        await download_manager.broadcast_progress()
        while True:
            data = await websocket.receive_text()
            # We don't really expect data from client in this simple setup
    except WebSocketDisconnect:
        download_manager.websockets.remove(websocket)

# Mount frontend
# Note: Ensure we don't crash if frontend dir doesn't exist yet during initial dev
os.makedirs("/app/frontend", exist_ok=True)
app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
