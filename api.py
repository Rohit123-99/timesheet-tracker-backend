from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import database
import pdf_export
import sprint_importer
from datetime import datetime, timedelta
import os
import json
import secrets

app = FastAPI(title="Timesheet Tracker API")


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# The API binds to 127.0.0.1 only, but a stale `allow_origins=["*"]` meant any
# website you visited could fetch your local task data via the browser. Lock
# CORS to the trusted UI origins and to the desktop scheme used by pywebview.
ALLOWED_ORIGINS = [
    "http://localhost:3000",   # vite dev server
    "http://127.0.0.1:3000",
    "http://localhost:5173",   # vite default port (covers `npm run dev` defaults)
    "http://127.0.0.1:5173",
    "null",                    # pywebview loads index.html via file:// -> origin=null
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Per-process secret. The UI fetches it once via GET /api/auth/token (from a
# trusted origin) and includes it on state-changing requests as
# `X-Timesheet-Token`. This is intentionally lightweight: the threat model is
# "another browser tab on this machine", not network attackers — uvicorn is
# bound to 127.0.0.1. Set TIMESHEET_DISABLE_AUTH=1 to opt out entirely.
SESSION_TOKEN = secrets.token_urlsafe(32)
_AUTH_DISABLED = os.environ.get("TIMESHEET_DISABLE_AUTH", "").strip() == "1"
_AUTH_REQUIRED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUTH_EXEMPT_PATHS = {"/api/auth/token", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def require_token_for_mutations(request: Request, call_next):
    if (
        not _AUTH_DISABLED
        and request.method in _AUTH_REQUIRED_METHODS
        and not any(request.url.path.startswith(p) for p in _AUTH_EXEMPT_PATHS)
    ):
        provided = request.headers.get("X-Timesheet-Token", "")
        if not secrets.compare_digest(provided, SESSION_TOKEN):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid X-Timesheet-Token header"},
            )
    return await call_next(request)


@app.get("/api/auth/token")
def get_session_token():
    """Hand the UI the per-process token. Browsers from other origins are
    blocked by CORS, so only the trusted UI can read it."""
    return {"token": SESSION_TOKEN, "auth_required": not _AUTH_DISABLED}


def _ensure_path_inside_user_home(path: str) -> str:
    """Reject path traversal by requiring the target to live under the user's
    home directory. Used by file-reading endpoints (sprint import)."""
    home = os.path.realpath(os.path.expanduser("~"))
    try:
        target = os.path.realpath(path)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path: {exc}")
    if not (target == home or target.startswith(home + os.sep)):
        raise HTTPException(
            status_code=403,
            detail=f"Path must be inside your home directory ({home})",
        )
    return target

# --- Pydantic Models for JSON Requests ---
class TaskCreate(BaseModel):
    task_name: str
    hours: float
    expected_hours: Optional[float] = 0.0
    notes: Optional[str] = ""
    date: str
    category: Optional[str] = ""

class TaskUpdate(BaseModel):
    task_name: str
    hours: float
    expected_hours: Optional[float] = 0.0
    notes: Optional[str] = ""
    date: str
    category: Optional[str] = ""

class SettingUpdate(BaseModel):
    value: str

class AllSettingsUpdate(BaseModel):
    target_hours: float
    weekly_target: float
    notifications: bool
    auto_save: bool

class ExportPdfRequest(BaseModel):
    filepath: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class SprintImportRequest(BaseModel):
    md_path: str
    start_date: str
    replace: Optional[bool] = False


class SprintImportInlineRequest(BaseModel):
    markdown: str
    start_date: str
    replace: Optional[bool] = False


def _resolve_range(start_date: Optional[str] = None, end_date: Optional[str] = None):
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end = datetime.now()
        start = end - timedelta(days=6)
    if start > end:
        start, end = end, start
    return start, end


def _build_report_payload(start: datetime, end: datetime):
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    tasks = database.get_weekly_tasks(start_str, end_str)
    target = float(database.get_setting("target_hours", "8.0"))

    span_days = (end.date() - start.date()).days + 1
    span_days = max(span_days, 1)

    daily_stats = []
    total_hours = 0.0

    for i in range(span_days):
        d = start + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        day_tasks = [t for t in tasks if t["date"] == d_str]
        day_total = sum(t["hours"] for t in day_tasks)
        total_hours += day_total
        daily_stats.append({
            "date": d_str,
            "day_name": d.strftime("%a"),
            "hours": day_total,
            "tasks": len(day_tasks)
        })

    return {
        "summary": {
            "total_weekly_hours": total_hours,
            "daily_average": total_hours / span_days,
            "daily_target": target
        },
        "daily_breakdown": daily_stats,
        "raw_tasks": tasks,
        "range": {
            "start_date": start_str,
            "end_date": end_str,
            "days": span_days
        }
    }

# --- Settings Endpoints ---
@app.get("/api/settings")
def get_all_settings():
    return {
        "target_hours": float(database.get_setting("target_hours", "8.0")),
        "weekly_target": float(database.get_setting("weekly_target", "40.0")),
        "notifications": database.get_setting("notifications", "true") == "true",
        "auto_save": database.get_setting("auto_save", "true") == "true"
    }

@app.put("/api/settings")
def update_all_settings(data: AllSettingsUpdate):
    database.set_setting("target_hours", str(data.target_hours))
    database.set_setting("weekly_target", str(data.weekly_target))
    database.set_setting("notifications", "true" if data.notifications else "false")
    database.set_setting("auto_save", "true" if data.auto_save else "false")
    return {"status": "success"}

@app.get("/api/settings/target_hours")
def get_target_hours():
    val = database.get_setting("target_hours", "8.0")
    return {"target_hours": float(val)}

@app.post("/api/settings/target_hours")
def set_target_hours(data: SettingUpdate):
    try:
        val = float(data.value)
        database.set_setting("target_hours", str(val))
        return {"target_hours": val}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid hours value")

# --- Dashboard Summary ---
@app.get("/api/dashboard/summary/{date_str}")
def get_dashboard_summary(date_str: str):
    target = float(database.get_setting("target_hours", "8.0"))
    tasks = database.get_tasks_by_date(date_str)
    worked = database.get_total_hours_for_date(date_str)
    
    return {
        "target_hours": target,
        "worked_hours": worked,
        "remaining_hours": max(0.0, target - worked),
        "tasks_completed": len([t for t in tasks if t.get('hours', 0) > 0 and t.get('expected_hours', 1) > 0 and t.get('hours', 0) >= 0.8 * t.get('expected_hours', 1)]),
        "total_tasks": len(tasks)
    }

# --- Task Endpoints ---
@app.get("/api/tasks/{date_str}")
def get_tasks_for_date(date_str: str):
    return database.get_tasks_by_date(date_str)

@app.post("/api/tasks")
def create_task(task: TaskCreate):
    tid = database.add_task(
        task_name=task.task_name,
        hours=task.hours,
        expected_hours=task.expected_hours,
        notes=task.notes,
        date_str=task.date,
        category=task.category
    )
    return {"id": tid, "status": "success"}

@app.put("/api/tasks/{task_id}")
def edit_task(task_id: int, task: TaskUpdate):
    database.update_task(
        task_id=task_id,
        task_name=task.task_name,
        hours=task.hours,
        expected_hours=task.expected_hours,
        notes=task.notes,
        date_str=task.date,
        category=task.category
    )
    return {"id": task_id, "status": "success"}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    database.delete_task(task_id)
    return {"id": task_id, "status": "deleted"}

# --- Reports Endpoints ---
@app.get("/api/reports/weekly")
def get_weekly_report():
    start, end = _resolve_range()
    return _build_report_payload(start, end)


@app.get("/api/reports/range")
def get_report_for_range(start_date: str, end_date: str):
    start, end = _resolve_range(start_date, end_date)
    return _build_report_payload(start, end)

@app.get("/api/reports/export")
def export_weekly_pdf(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start, end = _resolve_range(start_date, end_date)
    payload = _build_report_payload(start, end)
    tasks = payload["raw_tasks"]
    total_weekly = payload["summary"]["total_weekly_hours"]
    target = payload["summary"]["daily_target"]

    metrics = {
        "total": total_weekly,
        "target": target,
        "average": payload["summary"]["daily_average"]
    }
    
    # Generate the PDF
    filepath = "Weekly_Report.pdf"
    pdf_export.generate_weekly_pdf(
        filepath=filepath,
        start_date_str=payload["range"]["start_date"],
        end_date_str=payload["range"]["end_date"],
        tasks=tasks,
        metrics=metrics
    )
    
    return FileResponse(filepath, media_type="application/pdf", filename=filepath)

@app.post("/api/reports/export/save")
def export_weekly_pdf_to_path(data: ExportPdfRequest):
    start, end = _resolve_range(data.start_date, data.end_date)
    payload = _build_report_payload(start, end)
    tasks = payload["raw_tasks"]
    total_weekly = payload["summary"]["total_weekly_hours"]
    target = payload["summary"]["daily_target"]

    metrics = {
        "total": total_weekly,
        "target": target,
        "average": payload["summary"]["daily_average"]
    }

    pdf_export.generate_weekly_pdf(
        filepath=data.filepath,
        start_date_str=payload["range"]["start_date"],
        end_date_str=payload["range"]["end_date"],
        tasks=tasks,
        metrics=metrics
    )
    return {"status": "success", "filepath": data.filepath}

@app.post("/api/import/sprint")
def import_sprint_from_path(payload: SprintImportRequest):
    """Read a sprint tracker markdown from disk and create Block A/B/C/D tasks."""
    safe_path = _ensure_path_inside_user_home(payload.md_path)
    if not os.path.isfile(safe_path):
        raise HTTPException(status_code=400, detail=f"File not found: {payload.md_path}")
    if os.path.getsize(safe_path) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Markdown file too large (>5 MB)")
    try:
        return sprint_importer.import_sprint_from_path(
            safe_path,
            payload.start_date,
            replace=bool(payload.replace),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}")


@app.post("/api/import/sprint/inline")
def import_sprint_from_inline(payload: SprintImportInlineRequest):
    """Accept markdown text directly (useful when the UI uploads a file from the browser)."""
    if len(payload.markdown) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Markdown payload too large (>5 MB)")
    try:
        return sprint_importer.import_sprint(
            payload.markdown,
            payload.start_date,
            replace=bool(payload.replace),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/export/all")
def export_all_data():
    now = datetime.now()
    payload = {
        "exported_at": now.isoformat(timespec="seconds"),
        "settings": database.get_all_settings(),
        "tasks": database.get_all_tasks()
    }

    filename = f"Timesheet_Data_{now.strftime('%Y%m%d_%H%M%S')}.json"
    filepath = filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return FileResponse(filepath, media_type="application/json", filename=filename)
