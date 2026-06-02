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
    force: bool = False

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})

@app.get("/api/license")
async def get_license():
    is_valid, max_uses = auth.get_license_info()
    if is_valid:
        used = auth.get_usage()
        return {"status": "ok", "used": used, "max_uses": max_uses, "remaining": max_uses - used}
    return {"status": "error", "message": "Invalid license"}

@app.post("/api/start")
async def start_process(req: StartRequest):
    global active_worker, message_queue
    
    if active_worker and active_worker.is_running:
        return {"status": "error", "message": "A process is already running."}
        
    # Pre-flight check cho số lượt còn lại
    if not req.force:
        is_valid, max_uses = auth.get_license_info()
        if not is_valid:
            return {"status": "error", "message": "Bản quyền không hợp lệ!"}
            
        used = auth.get_usage()
        remaining = max_uses - used
        if remaining <= 0:
            return {"status": "error", "message": "Bạn đã hết lượt sử dụng! Vui lòng nạp thêm Key mới."}
            
        try:
            from excel_reader import read_input_excel
            records = read_input_excel(req.excel_path)
            total = len(records)
            
            if req.resume:
                # Nếu chạy tiếp, trừ đi số dòng đã có trong log (đơn giản hóa thì bỏ qua check chi tiết)
                pass
            else:
                if total > remaining:
                    return {
                        "status": "confirm", 
                        "message": f"CẢNH BÁO: Danh sách của bạn có {total} hồ sơ, nhưng bạn chỉ còn {remaining} lượt.\n\nThiếu {total - remaining} lượt để chạy toàn bộ danh sách.\nBạn có muốn bắt đầu chạy {remaining} hồ sơ đầu tiên không?"
                    }
        except Exception as e:
            pass # Lỗi đọc file thì để worker tự báo lỗi sau
    
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
