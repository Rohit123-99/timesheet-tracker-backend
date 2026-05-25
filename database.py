import sqlite3
import os
import sys
from datetime import datetime

def _bundled_mode_flag():
    """When PyInstaller bundles us, build.py drops a sentinel `_app_mode_flag.py`
    into the package so runtime knows which build this is — independent of the
    .exe filename or any env var. Returns 'production'/'testing' or None.
    """
    try:
        from _app_mode_flag import APP_MODE  # type: ignore
        normalised = str(APP_MODE).strip().lower()
        if normalised in {"production", "prod"}:
            return "production"
        if normalised in {"testing", "test"}:
            return "testing"
    except Exception:
        pass
    return None


def _detect_app_mode():
    """Detect runtime mode in this order of precedence:

      1. Bundle sentinel file (`_app_mode_flag.py`) — set by PyInstaller build
      2. APP_MODE env var — `production`/`prod`, `testing`/`test`, `development`/`dev`
      3. Executable filename hint — "test" in sys.executable basename
      4. Frozen exe with no other hint → `production`
      5. Unfrozen (`python run.py`) with no other hint → `development`

    Returning `development` (instead of `production`) for plain `python run.py` is
    the key fix: it stops dev work from silently writing to your production DB.
    """
    bundled = _bundled_mode_flag()
    if bundled:
        return bundled

    env_mode = os.environ.get("APP_MODE", "").strip().lower()
    if env_mode in {"production", "prod"}:
        return "production"
    if env_mode in {"testing", "test"}:
        return "testing"
    if env_mode in {"development", "dev"}:
        return "development"

    exe_name = os.path.basename(sys.executable).lower()
    if "test" in exe_name:
        return "testing"

    if getattr(sys, "frozen", False):
        return "production"
    return "development"


APP_MODE = _detect_app_mode()


# Determine persistent path for the database
def get_db_path():
    """
    Database isolation strategy:
      - production:  %APPDATA%/TimesheetTracker/timesheet.db          (live exe)
      - testing:     %APPDATA%/TimesheetTracker/testing/timesheet_test.db
      - development: %APPDATA%/TimesheetTracker/dev/timesheet_dev.db  (python run.py)
    """
    app_name = "TimesheetTracker"

    if os.name == "nt":  # Windows
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:  # Linux/Mac
        base_dir = os.path.expanduser("~")

    root_dir = os.path.join(base_dir, app_name)

    if APP_MODE == "testing":
        db_dir = os.path.join(root_dir, "testing")
        db_file = "timesheet_test.db"
    elif APP_MODE == "development":
        db_dir = os.path.join(root_dir, "dev")
        db_file = "timesheet_dev.db"
    else:
        db_dir = root_dir
        db_file = "timesheet.db"

    try:
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, db_file)
    except PermissionError:
        # Fallback for restricted environments: keep mode-based file names locally.
        local_dir = os.path.dirname(os.path.abspath(__file__))
        local_file = {
            "testing": "timesheet_test.db",
            "development": "timesheet_dev.db",
        }.get(APP_MODE, "timesheet.db")
        return os.path.join(local_dir, local_file)

DB_PATH = get_db_path()


def _maybe_seed_dev_db_from_production() -> None:
    """One-time migration: when dev mode starts and `timesheet_dev.db` doesn't
    exist yet but `timesheet.db` does, copy it across so the user doesn't lose
    their existing work the first time they run after the isolation fix.

    Only triggers in development mode and only on first dev launch.
    """
    if APP_MODE != "development":
        return
    if os.path.exists(DB_PATH):
        return

    # Locate the prod DB alongside our dev DB
    prod_db = os.path.join(os.path.dirname(os.path.dirname(DB_PATH)), "timesheet.db")
    if not os.path.exists(prod_db):
        return

    try:
        import shutil
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        shutil.copy2(prod_db, DB_PATH)
    except Exception:
        # Best-effort — if it fails, init_db() will create a fresh empty DB instead.
        pass


_maybe_seed_dev_db_from_production()

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create Tasks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_name TEXT NOT NULL,
            hours REAL NOT NULL,
            expected_hours REAL DEFAULT 0.0,
            notes TEXT,
            date TEXT NOT NULL,
            category TEXT
        )
    ''')
    
    # Try adding expected_hours column if it doesn't exist (for existing DBs)
    try:
        cursor.execute("ALTER TABLE tasks ADD COLUMN expected_hours REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    # Create Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    
    # Initialize default target hours if not set
    cursor.execute('SELECT count(*) FROM settings WHERE key = ?', ("target_hours",))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ("target_hours", "8.0"))
        
    cursor.execute('SELECT count(*) FROM settings WHERE key = ?', ("weekly_target",))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ("weekly_target", "40.0"))

    cursor.execute('SELECT count(*) FROM settings WHERE key = ?', ("notifications",))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ("notifications", "true"))

    cursor.execute('SELECT count(*) FROM settings WHERE key = ?', ("auto_save",))
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (key, value) VALUES (?, ?)', ("auto_save", "true"))
        
    conn.commit()
    conn.close()

# Task Operations
def add_task(task_name, hours, expected_hours, notes, date_str, category=""):
    """Adds a new task to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (task_name, hours, expected_hours, notes, date, category)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (task_name, hours, expected_hours, notes, date_str, category))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def update_task(task_id, task_name, hours, expected_hours, notes, date_str, category=""):
    """Updates an existing task."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tasks
        SET task_name = ?, hours = ?, expected_hours = ?, notes = ?, date = ?, category = ?
        WHERE id = ?
    ''', (task_name, hours, expected_hours, notes, date_str, category, task_id))
    conn.commit()
    conn.close()

def delete_task(task_id):
    """Deletes a task by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

def get_tasks_by_date(date_str):
    """Returns a list of tasks for a specific date (YYYY-MM-DD)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE date = ? ORDER BY id DESC', (date_str,))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def get_weekly_tasks(start_date_str, end_date_str):
    """Returns tasks within a date range."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks WHERE date >= ? AND date <= ? ORDER BY date ASC',
                   (start_date_str, end_date_str))
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def get_all_tasks():
    """Returns all tasks ordered by date descending, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tasks ORDER BY date DESC, id DESC')
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return tasks

def get_total_hours_for_date(date_str):
    """Returns the total hours logged for a specific date."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(hours) FROM tasks WHERE date = ?', (date_str,))
    total = cursor.fetchone()[0]
    conn.close()
    return total if total else 0.0

# Settings Operations
def get_setting(key, default_value=None):
    """Gets a setting value."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default_value

def set_setting(key, value):
    """Sets or updates a setting."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value)
        VALUES (?, ?)
    ''', (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings():
    """Returns all settings as a key/value dict."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

# Initialize DB when module is imported
init_db()
