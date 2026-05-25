import os
import sys
import time
import threading
import urllib.request
import urllib.error
from typing import Optional

import uvicorn
import webview


HOST = "127.0.0.1"
PORT = 8000
SERVER_URL = f"http://{HOST}:{PORT}/"
HEALTH_URL = f"http://{HOST}:{PORT}/api/settings"


def resource_path(relative_path: str) -> str:
    """Resolve a path to a resource bundled by PyInstaller (or relative to
    this file in dev mode)."""
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Change cwd to the bundle path when running as an exe
if getattr(sys, "frozen", False):
    os.chdir(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))


def start_server() -> None:
    """Run uvicorn in this thread. `api` is imported lazily so the env is
    set up first."""
    import api  # noqa: F401  (also triggers UI mount discovery)
    uvicorn.run(api.app, host=HOST, port=PORT, log_level="error")


def wait_for_server(timeout_seconds: float = 15.0) -> bool:
    """Poll /api/settings until it returns 200 (or until timeout). Prevents
    the window opening to a connection-refused page."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.15)
    return False


class ApiBridge:
    """JS-callable bridge exposed via pywebview's js_api."""

    def save_file_dialog(self, default_name: str = "Weekly_Report.pdf") -> Optional[str]:
        window = webview.windows[0] if webview.windows else None
        if not window:
            return None
        selection = window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=("PDF files (*.pdf)",),
        )
        if not selection:
            return None
        return selection if isinstance(selection, str) else selection[0]

    def minimize_window(self) -> bool:
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.minimize()
            return True
        except Exception:
            return False

    def toggle_fullscreen_window(self) -> bool:
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.toggle_fullscreen()
            return True
        except Exception:
            return False

    def close_window(self) -> bool:
        window = webview.windows[0] if webview.windows else None
        if not window:
            return False
        try:
            window.destroy()
            return True
        except Exception:
            return False


if __name__ == "__main__":
    # Start FastAPI in the background then wait for it to be reachable.
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    if not wait_for_server():
        print(
            f"WARNING: API server did not respond at {HEALTH_URL} within timeout. "
            "The window will open anyway but the UI may show 'Failed to fetch'."
        )
    else:
        print(f"API server ready at {SERVER_URL}")

    print(f"Opening desktop window at {SERVER_URL}")

    webview.create_window(
        "Timesheet Tracker",
        SERVER_URL,
        js_api=ApiBridge(),
        width=1200,
        height=800,
        min_size=(900, 600),
        fullscreen=True,
        background_color="#1A1A1A",
    )

    webview.start(private_mode=False)
