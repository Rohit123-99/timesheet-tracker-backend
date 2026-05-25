import os
import sys
import time
import threading
import subprocess
import xml.sax.saxutils as _xml_escape
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


def _show_windows_toast(title: str, body: str, scenario: str = "reminder") -> bool:
    """Show a native Windows 10/11 toast notification.

    Uses PowerShell + Windows Runtime so we don't have to bundle an extra
    Python dep. The toast appears in the Action Center on top of whatever
    app the user is currently focused on, plays the Windows alarm sound,
    and stays on screen until dismissed (scenario='reminder' + duration=long).
    """
    if os.name != "nt":
        return False

    # Escape XML and PowerShell single-quote-string special chars
    xml_title = _xml_escape.escape(title)
    xml_body = _xml_escape.escape(body)
    ps_title = xml_title.replace("'", "''")
    ps_body = xml_body.replace("'", "''")

    # `scenario="reminder"` keeps the toast on screen until dismissed and
    # plays the looping alarm sound. `duration="long"` is the fallback for
    # older WinRT versions that don't understand scenario.
    ps_script = (
        '$ErrorActionPreference = "SilentlyContinue"; '
        '[Windows.UI.Notifications.ToastNotificationManager, '
        'Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; '
        '[Windows.UI.Notifications.ToastNotification, '
        'Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; '
        '[Windows.Data.Xml.Dom.XmlDocument, '
        'Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null; '
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; "
        f"$xml.LoadXml('<toast scenario=\"{scenario}\" duration=\"long\">"
        '<visual><binding template=\"ToastGeneric\">'
        f"<text>{ps_title}</text>"
        f"<text>{ps_body}</text>"
        '</binding></visual>'
        '<audio src=\"ms-winsoundevent:Notification.Looping.Alarm\" loop=\"true\"/>'
        '<actions>'
        '<action content=\"Dismiss\" arguments=\"dismiss\" activationType=\"system\"/>'
        '</actions>'
        "</toast>'); "
        '$toast = New-Object Windows.UI.Notifications.ToastNotification $xml; '
        '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('
        '"Timesheet Tracker").Show($toast)'
    )

    try:
        flags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            flags = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-Command", ps_script,
            ],
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as exc:
        print(f"Toast failed: {exc}")
        return False


class ApiBridge:
    """JS-callable bridge exposed via pywebview's js_api."""

    def show_notification(self, title: str, body: str) -> bool:
        """Pop a Windows toast (Action Center popup) outside the app window.

        Called from the React PomodoroWidget whenever a phase ends — so the
        user sees the alarm even when working in a different app. Runs the
        PowerShell subprocess on a background thread so the JS-side promise
        resolves immediately.
        """
        threading.Thread(
            target=_show_windows_toast,
            args=(title, body),
            daemon=True,
        ).start()
        return True

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
