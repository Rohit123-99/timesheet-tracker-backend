# Personal Timesheet Tracker (Backend + Desktop Launcher)

Offline Windows productivity application for tracking daily work hours, tasks, weekly analytics, and PDF exports.

This repository contains the Python backend and desktop launcher (`pywebview`).  
Backend and UI code are maintained in separate GitHub repositories.

All application data is stored locally (SQLite). No cloud service is required.

## Project Overview
- Backend API built with FastAPI
- Local SQLite storage for tasks and settings
- Desktop app shell via `pywebview`
- PDF report export via ReportLab
- React/Vite frontend served as local static build in desktop mode

## Features
- Daily dashboard with goal tracking
- Task management (add, edit, delete, complete/incomplete)
- Weekly analytics
- Export weekly PDF reports
- Local-first/offline operation

## Prerequisites (Windows)
- Python `3.12` (recommended)
- Node.js `18+` and npm
- Git (optional, for cloning)

## Installation Steps

### 1) UI setup (frontend)
```bat
cd ..\frontend
npm install
npm run build
```

### 2) Backend setup
```bat
cd ..\backend
py -3.12 -m venv .venv
.\.venv\Scripts\activate.bat
python -m ensurepip --upgrade
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Running the Application Locally

### Recommended: Desktop mode (backend + UI in one step)
From `backend`:
```bat
.\.venv\Scripts\activate.bat
python run.py
```

Startup validation:
- Console should print:  
  `Using UI file: ...\frontend\dist\index.html`

### Development mode (run API + UI separately)
Terminal 1 (backend API):
```bat
cd backend
.\.venv\Scripts\activate.bat
uvicorn api:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 (frontend):
```bat
cd frontend
npm run dev
```

Open in browser: `http://localhost:3000`

## Building Windows Executable (.exe)

### Tool used
- PyInstaller (recommended)
- Electron is **not applicable** for this project because desktop packaging is already handled by Python + pywebview.

### Build command (exact)
From `backend`:
```bat
.\.venv\Scripts\activate.bat
python -m pip install pyinstaller
pyinstaller --noconfirm --windowed --onefile --name "TimesheetTracker" --add-data "..\frontend\dist;ui" run.py
```

Output:
- `backend\dist\TimesheetTracker.exe`

## Project Structure
```text
timesheet-tracker-separated/
  backend/
    api.py
    database.py
    pdf_export.py
    run.py
    requirements.txt
  frontend/
    src/
    package.json
    vite.config.ts
    dist/              (generated)
```

## Repository Split (GitHub)
- Backend repository: this repo (Python API + desktop launcher)
- UI repository: separate React/Vite repo
- Keep both repos in sibling folders locally:
  - `...\backend`
  - `...\frontend`
- Desktop launcher in backend loads UI build from `..\frontend\dist\index.html`


## Troubleshooting Tips

### 1) `localhost refused to connect` in desktop window
- Ensure frontend build exists:
  ```bat
  cd ..\frontend
  npm run build
  ```
- Re-run:
  ```bat
  cd ..\backend
  python run.py
  ```
- Check for `Using UI file: ...\frontend\dist\index.html`

### 2) `No module named pip`
- Make sure venv is activated in `cmd`:
  ```bat
  .\.venv\Scripts\activate.bat
  python -m ensurepip --upgrade
  ```

### 3) Wrong Python version used
- Verify executable path:
  ```bat
  python -c "import sys; print(sys.executable)"
  ```
- Should point to `...\backend\.venv\Scripts\python.exe`

### 4) UI changes not visible
- Rebuild frontend:
  ```bat
  cd ..\frontend
  npm run build
  ```
- Restart `python run.py`
