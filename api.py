from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import database
import pdf_export
from datetime import datetime, timedelta
from fastapi.responses import FileResponse
import os
import json

app = FastAPI(title="Timesheet Tracker API")

# Allow the separate Vite server to hit the local Python API during dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    today = datetime.now()
    start_date = today - timedelta(days=6)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")
    
    tasks = database.get_weekly_tasks(start_str, end_str)
    target = float(database.get_setting("target_hours", "8.0"))
    
    # Pre-fill daily hours
    daily_stats = []
    total_weekly = 0.0
    
    for i in range(7):
        d = start_date + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        day_tasks = [t for t in tasks if t["date"] == d_str]
        
        day_total = sum(t["hours"] for t in day_tasks)
        total_weekly += day_total
        
        daily_stats.append({
            "date": d_str,
            "day_name": d.strftime("%a"),
            "hours": day_total,
            "tasks": len(day_tasks)
        })
        
    return {
        "summary": {
            "total_weekly_hours": total_weekly,
            "daily_average": total_weekly / 7.0,
            "daily_target": target
        },
        "daily_breakdown": daily_stats,
        "raw_tasks": tasks
    }

@app.get("/api/reports/export")
def export_weekly_pdf():
    today = datetime.now()
    start_date = today - timedelta(days=6)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")
    
    tasks = database.get_weekly_tasks(start_str, end_str)
    target = float(database.get_setting("target_hours", "8.0"))
    
    total_weekly = sum(t["hours"] for t in tasks)
    
    metrics = {
        "total": total_weekly,
        "target": target,
        "average": total_weekly / 7.0
    }
    
    # Generate the PDF
    filepath = "Weekly_Report.pdf"
    pdf_export.generate_weekly_pdf(
        filepath=filepath,
        start_date_str=start_str,
        end_date_str=end_str,
        tasks=tasks,
        metrics=metrics
    )
    
    return FileResponse(filepath, media_type="application/pdf", filename=filepath)

@app.post("/api/reports/export/save")
def export_weekly_pdf_to_path(data: ExportPdfRequest):
    today = datetime.now()
    start_date = today - timedelta(days=6)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today.strftime("%Y-%m-%d")

    tasks = database.get_weekly_tasks(start_str, end_str)
    target = float(database.get_setting("target_hours", "8.0"))
    total_weekly = sum(t["hours"] for t in tasks)

    metrics = {
        "total": total_weekly,
        "target": target,
        "average": total_weekly / 7.0
    }

    pdf_export.generate_weekly_pdf(
        filepath=data.filepath,
        start_date_str=start_str,
        end_date_str=end_str,
        tasks=tasks,
        metrics=metrics
    )
    return {"status": "success", "filepath": data.filepath}

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
