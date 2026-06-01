import asyncio
import queue
import os
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
import auth
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from web_worker import WebWorker

app = FastAPI()

# Make sure templates dir exists
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATES_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

active_worker: WebWorker | None = None
message_queue: queue.Queue = queue.Queue()

class StartRequest(BaseModel):
    excel_path: str
    photo_folder: str
    resume: bool = False
    threads: int = 1
    headless: bool = True

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

@app.post("/api/start")
async def start_process(req: StartRequest):
    global active_worker, message_queue
    
    if active_worker and active_worker.is_running:
        return {"status": "error", "message": "A process is already running."}
    
    # Clear the queue
    while not message_queue.empty():
        try:
            message_queue.get_nowait()
        except queue.Empty:
            break

    active_worker = WebWorker(req.excel_path, req.photo_folder, message_queue, req.resume, req.threads, req.headless)
    active_worker.start()
    
    return {"status": "success", "message": "Started processing"}

@app.post("/api/stop")
async def stop_process():
    global active_worker
    if active_worker and active_worker.is_running:
        active_worker.stop()
        return {"status": "success", "message": "Stopping process..."}
    return {"status": "error", "message": "No active process to stop."}

@app.post("/api/logout")
async def logout(background_tasks: BackgroundTasks):
    auth.remove_license()
    
    def shutdown():
        import time
        time.sleep(1)
        os._exit(0)
        
    background_tasks.add_task(shutdown)
    return {"status": "success", "message": "Đã đăng xuất"}

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Poll the queue (non-blocking)
            try:
                # Use to_thread to avoid blocking the event loop while waiting briefly
                msg = await asyncio.to_thread(message_queue.get, True, 0.1)
                await websocket.send_json(msg)
                message_queue.task_done()
            except queue.Empty:
                await asyncio.sleep(0.05)
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
