import uvicorn
import webview
import threading
import os
import sys
from typing import Optional

# Helper to get paths for bundled files
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Change working dir to the bundle path if running as exe
if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Only start the server if we're generating the executable
def start_server():
    import api  # Import here to ensure it's in the same process/thread context
    uvicorn.run(api.app, host="127.0.0.1", port=8000, log_level="error")


class ApiBridge:
    def save_file_dialog(self, default_name: str = "Weekly_Report.pdf") -> Optional[str]:
        window = webview.windows[0] if webview.windows else None
        if not window:
            return None
        selection = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=("PDF files (*.pdf)",)
        )
        if not selection:
            return None
        return selection if isinstance(selection, str) else selection[0]

    def minimize_window(self):
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.minimize()
            return True
        except Exception:
            return False

    def toggle_fullscreen_window(self):
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.toggle_fullscreen()
            return True
        except Exception:
            return False

    def close_window(self):
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.destroy()
            return True
        except Exception:
            return False

if __name__ == "__main__":
    # Start the FastAPI server on a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Use local build first in development so desktop runs latest UI without manual copy.
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        candidate_paths = [resource_path(os.path.join('ui', 'index.html'))]
    else:
        candidate_paths = [
            os.path.join(base_dir, '..', 'frontend', 'dist', 'index.html'),
            os.path.join(base_dir, 'ui', 'index.html'),
        ]
    url = None
    for path in candidate_paths:
        if os.path.exists(path):
            url = path
            break
    if not url:
        url = "http://localhost:3000"
        print("Warning: Bundled UI not found. Using dev fallback http://localhost:3000")
    else:
        print(f"Using UI file: {url}")

    print("Launching Timesheet Tracker Window...")
    
    webview.create_window(
        'Timesheet Tracker', 
        url, 
        js_api=ApiBridge(),
        width=1200, 
        height=800,
        min_size=(900, 600),
        fullscreen=True,
        background_color='#1A1A1A'
    )
    
    webview.start(private_mode=False)
