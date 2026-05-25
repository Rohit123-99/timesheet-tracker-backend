"""SDET sprint plan importer.

Parses an SDET Sprint markdown tracker (the one generated under
`Study Tracking/SDET_Sprint_Tracker.md`) and turns each day's four work
blocks (Block A/B/C/D) into individual tasks in the timesheet DB.

Produces one task per block per day:
  - task_name: "Day NN \xb7 Block X — <verb>"
  - expected_hours: parsed from the (Nh) suffix in the source line
  - notes: block description (+ deliverables checklist on Block D)
  - date: start_date + (day_number - 1) days
  - category: "SDET Sprint"

The DB schema is unchanged — we just write rows via database.add_task.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import database


SPRINT_CATEGORY = "SDET Sprint"

# Match a day section header, e.g. "## Day 01 — Pytest fundamentals"
_DAY_HEADER_RE = re.compile(r"^##\s+Day\s+(\d{1,2})\s+[—\-]\s+(.+?)\s*$", re.MULTILINE)
# Match a block line in the "Work blocks" subsection, e.g.
#   "- [ ] **Block A — Learn (1.5h):** read concepts ..."
_BLOCK_LINE_RE = re.compile(
    r"^[ \t]*-[ \t]*\[[ xX]\][ \t]+\*\*Block[ \t]+([ABCD])[ \t]+[—\-][ \t]+([^(\n]+?)\((\d+(?:\.\d+)?)h\):?\*\*[ \t]*([^\n]*)$",
    re.MULTILINE,
)
# Match a deliverables checklist item: "- [ ] some text"
_DELIVERABLE_RE = re.compile(r"^-\s*\[[ xX]\]\s+(?!\*\*Block)(.+?)\s*$", re.MULTILINE)
# Match the "**Theme:**" line
_THEME_RE = re.compile(r"^\*\*Theme:\*\*\s+(.+?)\s*$", re.MULTILINE)
# Match the "**Branch:**" line; branch may be in backticks
_BRANCH_RE = re.compile(r"^\*\*Branch:\*\*\s+`?([^`\n]+?)`?\s*(\(.*\))?\s*$", re.MULTILINE)


@dataclass
class SprintBlock:
    letter: str        # "A" | "B" | "C" | "D"
    verb: str          # "Learn" | "Build" | "Practice" | "Polish & Ship"
    hours: float       # 1.5 / 3 / 2 / 1
    description: str   # text after the colon


@dataclass
class SprintDay:
    number: int                          # 1..14
    title: str                           # e.g. "Pytest fundamentals"
    theme: str = ""
    branch: str = ""
    blocks: list[SprintBlock] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)


def parse_tracker(markdown: str) -> list[SprintDay]:
    """Parse the SDET sprint tracker markdown into structured days.

    Only days 1–14 are returned (Day 00 is skipped — it's already done).
    """
    headers = list(_DAY_HEADER_RE.finditer(markdown))
    days: list[SprintDay] = []

    for idx, match in enumerate(headers):
        day_num = int(match.group(1))
        title = match.group(2).strip()
        if day_num == 0:
            continue

        section_start = match.end()
        section_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(markdown)
        section = markdown[section_start:section_end]

        day = SprintDay(number=day_num, title=title)

        theme_match = _THEME_RE.search(section)
        if theme_match:
            day.theme = theme_match.group(1).strip()

        branch_match = _BRANCH_RE.search(section)
        if branch_match:
            day.branch = branch_match.group(1).strip()

        for block_match in _BLOCK_LINE_RE.finditer(section):
            day.blocks.append(SprintBlock(
                letter=block_match.group(1),
                verb=block_match.group(2).strip(),
                hours=float(block_match.group(3)),
                description=block_match.group(4).strip(),
            ))

        # Deliverables live in a sub-section beginning with "### End-of"
        deliv_marker = re.search(r"###\s+End-of[^\n]*\n", section)
        if deliv_marker:
            deliv_block = section[deliv_marker.end():]
            # Stop at the next '###' or '**Date done:**' line
            stop = re.search(r"^(###|\*\*Date done|---)", deliv_block, re.MULTILINE)
            if stop:
                deliv_block = deliv_block[:stop.start()]
            for d_match in _DELIVERABLE_RE.finditer(deliv_block):
                day.deliverables.append(d_match.group(1).strip())

        days.append(day)

    return days


def _format_block_task_name(day: SprintDay, block: SprintBlock) -> str:
    return f"Day {day.number:02d} \xb7 Block {block.letter} — {block.verb}"


def _format_block_notes(day: SprintDay, block: SprintBlock) -> str:
    lines = [f"Day {day.number:02d}: {day.title}"]
    if day.theme:
        lines.append(f"Theme: {day.theme}")
    if day.branch:
        lines.append(f"Branch: {day.branch}")
    lines.append("")
    lines.append(block.description)

    # Block D is the wrap-up — attach the deliverables checklist for context.
    if block.letter == "D" and day.deliverables:
        lines.append("")
        lines.append("End-of-day deliverables:")
        for item in day.deliverables:
            lines.append(f"  [ ] {item}")

    return "\n".join(lines).strip()


def _existing_sprint_keys() -> set[tuple[str, str]]:
    """Return the set of (task_name, date) pairs already imported."""
    keys: set[tuple[str, str]] = set()
    for row in database.get_all_tasks():
        if (row.get("category") or "") == SPRINT_CATEGORY:
            keys.add((row["task_name"], row["date"]))
    return keys


def _delete_existing_sprint_tasks() -> int:
    """Hard-delete every task in the SDET Sprint category. Returns count removed."""
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tasks WHERE category = ?", (SPRINT_CATEGORY,))
    ids = [row[0] for row in cursor.fetchall()]
    cursor.executemany("DELETE FROM tasks WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return len(ids)


def import_sprint(
    markdown: str,
    start_date: str,
    *,
    replace: bool = False,
) -> dict:
    """Parse `markdown` and create one task per (day, block).

    Args:
        markdown: Full text of SDET_Sprint_Tracker.md.
        start_date: "YYYY-MM-DD" — the date assigned to Day 1.
        replace:  If True, delete all existing SDET Sprint tasks first.

    Returns a dict with created/skipped/deleted counts.
    """
    try:
        anchor = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"start_date must be YYYY-MM-DD: {exc}") from exc

    days = parse_tracker(markdown)
    if not days:
        raise ValueError("No 'Day NN — ...' sections found in markdown")

    deleted = _delete_existing_sprint_tasks() if replace else 0
    existing_keys = set() if replace else _existing_sprint_keys()

    created = 0
    skipped = 0
    created_items: list[dict] = []

    for day in days:
        day_date = (anchor + timedelta(days=day.number - 1)).strftime("%Y-%m-%d")
        for block in day.blocks:
            task_name = _format_block_task_name(day, block)
            if (task_name, day_date) in existing_keys:
                skipped += 1
                continue
            database.add_task(
                task_name=task_name,
                hours=0.0,
                expected_hours=block.hours,
                notes=_format_block_notes(day, block),
                date_str=day_date,
                category=SPRINT_CATEGORY,
            )
            created += 1
            created_items.append({
                "day": day.number,
                "block": block.letter,
                "date": day_date,
                "task_name": task_name,
            })

    return {
        "status": "success",
        "start_date": start_date,
        "end_date": (anchor + timedelta(days=days[-1].number - 1)).strftime("%Y-%m-%d"),
        "days_parsed": len(days),
        "created": created,
        "skipped": skipped,
        "deleted": deleted,
        "tasks": created_items,
    }


def import_sprint_from_path(
    md_path: str,
    start_date: str,
    *,
    replace: bool = False,
) -> dict:
    """Convenience wrapper that reads the file then calls import_sprint."""
    with open(md_path, "r", encoding="utf-8") as handle:
        text = handle.read()
    return import_sprint(text, start_date, replace=replace)


# Allow running as a one-off CLI: `python sprint_importer.py <md> <YYYY-MM-DD> [--replace]`
if __name__ == "__main__":  # pragma: no cover
    import argparse, json
    parser = argparse.ArgumentParser(description="Import an SDET sprint markdown tracker")
    parser.add_argument("md_path", help="Path to SDET_Sprint_Tracker.md")
    parser.add_argument("start_date", help="YYYY-MM-DD assigned to Day 1")
    parser.add_argument("--replace", action="store_true", help="Wipe existing SDET Sprint tasks first")
    args = parser.parse_args()
    result = import_sprint_from_path(args.md_path, args.start_date, replace=args.replace)
    print(json.dumps(result, indent=2))
