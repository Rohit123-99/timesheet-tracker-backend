"""Quick smoke test for the Pomodoro -> task-log flow.

This script reproduces, at the HTTP layer, exactly what the PomodoroWidget
does when a 25-minute focus session ends. You do NOT need to wait 25 minutes:
the test runs in <1 second against the already-running app.

Assumptions:
  - One of timesheet.exe / timesheet-test.exe is running on 127.0.0.1:8000
  - You have write access (the script fetches the per-process auth token)

Run (from the backend folder, venv activated):
  python test_pomodoro_flow.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

API_BASE = "http://127.0.0.1:8000/api"
FOCUS_MINUTES = 25                          # what the widget uses
EXPECTED_HOURS_DELTA = FOCUS_MINUTES / 60   # 0.4166...


def _req(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"} if body is not None else {}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {e.code} {body_text}") from None


def step(label: str, fn):
    print(f"  - {label}", end=" ", flush=True)
    try:
        result = fn()
        print("OK")
        return result
    except Exception as exc:
        print(f"FAIL\n    {exc}")
        sys.exit(1)


def main():
    print("Pomodoro -> task-log smoke test")
    print(f"  API base: {API_BASE}")
    print()

    # 1. Make sure the API is reachable
    print("1. Health check")
    settings = step("GET /api/settings", lambda: _req("GET", "/settings"))
    print(f"      daily target = {settings.get('target_hours')}h")

    # 2. Fetch the session token (UI does this once at boot)
    print("\n2. Auth token (simulates the UI's boot fetch)")
    token_resp = step("GET /api/auth/token", lambda: _req("GET", "/auth/token"))
    token = token_resp["token"]
    auth_required = token_resp.get("auth_required", True)
    print(f"      token = {token[:12]}…  auth_required = {auth_required}")

    auth_header = {"X-Timesheet-Token": token}

    # 3. Create a brand-new task today
    today = datetime.now().strftime("%Y-%m-%d")
    initial_hours = 1.0
    test_name = f"pomodoro-flow-test {datetime.now().strftime('%H:%M:%S')}"
    print(f"\n3. Create a test task (date={today}, initial actual={initial_hours}h)")
    create_resp = step(
        "POST /api/tasks",
        lambda: _req(
            "POST",
            "/tasks",
            {
                "task_name": test_name,
                "hours": initial_hours,
                "expected_hours": 2.0,
                "notes": "Created by test_pomodoro_flow.py",
                "date": today,
                "category": "test",
            },
            headers=auth_header,
        ),
    )
    task_id = create_resp["id"]
    print(f"      created task id = {task_id}")

    # 4. Simulate what handleFocusComplete does at the end of a 25-min focus
    #    session: PUT the task back with hours += FOCUS_MINUTES / 60
    new_hours = round(initial_hours + EXPECTED_HOURS_DELTA, 2)
    print(f"\n4. Simulate focus-end: add {FOCUS_MINUTES} minutes (= +{EXPECTED_HOURS_DELTA:.4f}h)")
    print(f"      expected actual after update: {new_hours}h")
    step(
        f"PUT /api/tasks/{task_id}",
        lambda: _req(
            "PUT",
            f"/tasks/{task_id}",
            {
                "task_name": test_name,
                "hours": new_hours,
                "expected_hours": 2.0,
                "notes": "Updated by test_pomodoro_flow.py (simulating Pomodoro end)",
                "date": today,
                "category": "test",
            },
            headers=auth_header,
        ),
    )

    # 5. Read it back
    print("\n5. Read the task back to verify the math")
    tasks = step(f"GET /api/tasks/{today}", lambda: _req("GET", f"/tasks/{today}"))
    matching = [t for t in tasks if t["id"] == task_id]
    if not matching:
        print(f"FAIL: task {task_id} not found in GET response")
        sys.exit(1)
    actual = float(matching[0]["hours"])
    if abs(actual - new_hours) > 1e-6:
        print(f"FAIL: read back {actual}h, expected {new_hours}h")
        sys.exit(1)
    print(f"      read-back actual = {actual}h [OK]")

    # 6. Confirm a POST without the token is rejected (security still on)
    print("\n6. Security check: same PUT without token must be 401")
    try:
        _req(
            "PUT",
            f"/tasks/{task_id}",
            {
                "task_name": test_name, "hours": 999.0, "expected_hours": 2.0,
                "notes": "", "date": today, "category": "test",
            },
        )
        print("      FAIL: unauthenticated PUT was accepted (should have been 401)")
        sys.exit(1)
    except RuntimeError as exc:
        msg = str(exc)
        if "401" in msg:
            print("      401 returned [OK] (rejection works)")
        else:
            print(f"      FAIL: expected 401, got: {msg}")
            sys.exit(1)

    # 7. Clean up
    print("\n7. Clean up test task")
    step(f"DELETE /api/tasks/{task_id}", lambda: _req("DELETE", f"/tasks/{task_id}", headers=auth_header))

    print("\nALL CHECKS PASSED")
    print(f"  - Token round-trip works")
    print(f"  - PUT with token updates hours (+{EXPECTED_HOURS_DELTA:.4f}h)")
    print(f"  - PUT without token is blocked (401)")
    print(f"  - The exact API call the PomodoroWidget makes at end-of-focus")
    print(f"    is verified to work end-to-end against the running app.")


if __name__ == "__main__":
    main()
