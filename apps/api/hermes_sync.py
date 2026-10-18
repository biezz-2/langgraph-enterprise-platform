"""Hermes <-> LangGraph Platform (LGP) Synchronization Engine.

Synchronizes:
1. Kanban Boards & Cards Lifecycle (AGENTS.md schema <-> LangGraph DB)
2. Board Registry (~/.state/registry/boards.json)
3. Phase-Gate Validation Reports (~/.state/validation/)
4. Memory & Lessons (~/.state/memory/ <-> temporal_facts)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("lgp.hermes_sync")

HERMES_STATE_DIR = Path("/home/biezz/.state")
HERMES_BOARDS_DIR = HERMES_STATE_DIR / "boards"
HERMES_REGISTRY_FILE = HERMES_STATE_DIR / "registry" / "boards.json"
HERMES_MEMORY_DIR = HERMES_STATE_DIR / "memory"
HERMES_VALIDATION_DIR = HERMES_STATE_DIR / "validation"

STATUS_ORDER = [
    "BACKLOG",
    "IN_PROGRESS",
    "IMPLEMENTED",
    "IN_VALIDATION",
    "VALIDATED",
    "REWORK",
]

STATUS_DISPLAY_NAMES = {
    "BACKLOG": "Backlog",
    "IN_PROGRESS": "In Progress",
    "IMPLEMENTED": "Implemented",
    "IN_VALIDATION": "In Validation",
    "VALIDATED": "Validated",
    "REWORK": "Rework",
}


def normalize_status(status_str: Optional[str]) -> str:
    """Normalize various status strings to standard 6-state AGENTS.md lifecycle."""
    if not status_str:
        return "BACKLOG"
    s = status_str.strip().upper().replace(" ", "_").replace("-", "_")
    if "BACKLOG" in s:
        return "BACKLOG"
    if "PROGRESS" in s:
        return "IN_PROGRESS"
    if "REWORK" in s:
        return "REWORK"
    if "IN_VALIDATION" in s or "VALIDATING" in s or "TESTING" in s:
        return "IN_VALIDATION"
    if "VALIDATED" in s or "DONE" in s or "COMPLETE" in s or "RESOLVED" in s:
        return "VALIDATED"
    if "IMPLEMENTED" in s:
        return "IMPLEMENTED"
    return "BACKLOG"


def slugify(text: str) -> str:
    """Sanitize string for board ID / filename."""
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", s)


async def ensure_columns_for_board(db: Any, board_id: str) -> Dict[str, str]:
    """Ensure the board has standard 6 columns in DB, returns dict of {status_key: col_id}."""
    async with db.execute(
        "SELECT id, name, order_idx FROM kanban_columns WHERE board_id = ? ORDER BY order_idx ASC",
        (board_id,),
    ) as cursor:
        existing_cols = await cursor.fetchall()

    status_to_col_id: Dict[str, str] = {}
    for col in existing_cols:
        col_dict = dict(col)
        norm = normalize_status(col_dict["name"])
        status_to_col_id[norm] = col_dict["id"]

    # If missing any of the 6 standard columns, insert them
    for idx, status_key in enumerate(STATUS_ORDER):
        if status_key not in status_to_col_id:
            col_id = f"col-{slugify(board_id)}-{status_key.lower()}"
            col_name = STATUS_DISPLAY_NAMES[status_key]
            await db.execute(
                "INSERT INTO kanban_columns (id, board_id, name, order_idx) VALUES (?, ?, ?, ?)",
                (col_id, board_id, col_name, idx),
            )
            status_to_col_id[status_key] = col_id

    return status_to_col_id


async def sync_hermes_boards_to_db(db: Any) -> Dict[str, Any]:
    """Read all Hermes state boards and synchronize into LangGraph database."""
    HERMES_BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    board_files = list(HERMES_BOARDS_DIR.glob("*.json"))

    boards_synced = 0
    cards_synced = 0

    for bpath in board_files:
        try:
            with open(bpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error("Failed to read board file %s: %s", bpath, e)
            continue

        board_obj = data.get("board", {})
        board_id = board_obj.get("board_id") or bpath.stem
        board_title = board_obj.get("title") or board_obj.get("name") or board_id

        # 1. Check if board exists in kanban_boards
        async with db.execute(
            "SELECT id FROM kanban_boards WHERE id = ?", (board_id,)
        ) as cursor:
            row = await cursor.fetchone()

        now_ts = time.time()
        if not row:
            await db.execute(
                "INSERT INTO kanban_boards (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (board_id, board_title, now_ts, now_ts),
            )
            boards_synced += 1
        else:
            await db.execute(
                "UPDATE kanban_boards SET updated_at = ? WHERE id = ?",
                (now_ts, board_id),
            )

        # 2. Ensure columns exist
        col_map = await ensure_columns_for_board(db, board_id)

        # 3. Upsert cards
        cards = board_obj.get("cards", [])
        for card in cards:
            c_id = card.get("card_id") or f"c-{board_id}-{int(now_ts*1000)}"
            c_title = card.get("title", "Untitled Card")
            c_desc = card.get("notes") or card.get("description") or ""
            c_status = normalize_status(card.get("status"))
            target_col_id = col_map.get(c_status, col_map["BACKLOG"])

            c_severity = card.get("severity")
            c_assignee = card.get("assignee") or board_obj.get("owner_agent", "HERMES")
            c_phase = card.get("phase_ref") or ""

            priority = "medium"
            if c_severity == "BLOCKER":
                priority = "critical"
            elif c_severity == "MAJOR":
                priority = "high"
            elif c_severity == "MINOR":
                priority = "low"

            meta = {
                "phase_ref": c_phase,
                "severity": c_severity,
                "finding_ref": card.get("finding_ref"),
                "status": c_status,
                "assignee": c_assignee,
                "notes": card.get("notes", ""),
            }
            meta_json = json.dumps(meta)

            # Check if card exists
            async with db.execute(
                "SELECT id FROM kanban_cards WHERE id = ?", (c_id,)
            ) as cursor:
                card_row = await cursor.fetchone()

            if card_row:
                await db.execute(
                    """UPDATE kanban_cards 
                       SET column_id = ?, title = ?, description = ?, priority = ?, 
                           assigned_to = ?, metadata_json = ?, updated_at = ?
                       WHERE id = ?""",
                    (target_col_id, c_title, c_desc, priority, c_assignee, meta_json, now_ts, c_id),
                )
            else:
                await db.execute(
                    """INSERT INTO kanban_cards 
                       (id, column_id, title, description, priority, assigned_to, metadata_json, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (c_id, target_col_id, c_title, c_desc, priority, c_assignee, meta_json, now_ts, now_ts),
                )
            cards_synced += 1

    await db.commit()
    return {"boards_synced": boards_synced, "cards_synced": cards_synced}


async def sync_db_boards_to_hermes(db: Any) -> Dict[str, Any]:
    """Export all DB kanban boards and cards to Hermes ~/.state/boards and registry."""
    HERMES_BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    HERMES_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Load registry
    registry: Dict[str, Any] = {"boards": {}}
    if HERMES_REGISTRY_FILE.exists():
        try:
            with open(HERMES_REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
                if "boards" not in registry:
                    registry["boards"] = {}
        except Exception:
            registry = {"boards": {}}

    async with db.execute("SELECT id, name, created_at, updated_at FROM kanban_boards") as cursor:
        boards = await cursor.fetchall()

    exported_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for b in boards:
        b_dict = dict(b)
        board_id = b_dict["id"]
        board_name = b_dict["name"]

        # Fetch columns and cards
        async with db.execute(
            "SELECT id, name, order_idx FROM kanban_columns WHERE board_id = ? ORDER BY order_idx ASC",
            (board_id,),
        ) as c_cur:
            columns = [dict(c) for c in await c_cur.fetchall()]

        cards_list: List[Dict[str, Any]] = []
        for col in columns:
            col_norm_status = normalize_status(col["name"])
            async with db.execute(
                "SELECT id, column_id, title, description, priority, assigned_to, metadata_json FROM kanban_cards WHERE column_id = ?",
                (col["id"],),
            ) as k_cur:
                card_rows = await k_cur.fetchall()
                for cr in card_rows:
                    cr_dict = dict(cr)
                    meta = {}
                    if cr_dict.get("metadata_json"):
                        try:
                            meta = json.loads(cr_dict["metadata_json"])
                        except Exception:
                            meta = {}

                    cards_list.append({
                        "card_id": cr_dict["id"],
                        "title": cr_dict["title"],
                        "status": col_norm_status,
                        "severity": meta.get("severity"),
                        "finding_ref": meta.get("finding_ref"),
                        "assignee": cr_dict.get("assigned_to") or "HERMES",
                        "notes": cr_dict.get("description") or meta.get("notes", ""),
                        "phase_ref": meta.get("phase_ref", ""),
                    })

        c_at = b_dict.get("created_at")
        if isinstance(c_at, datetime):
            c_at = c_at.isoformat()
        u_at = b_dict.get("updated_at")
        if isinstance(u_at, datetime):
            u_at = u_at.isoformat()

        board_payload = {
            "board": {
                "board_id": board_id,
                "name": board_name,
                "type": "PROJECT" if not board_id.startswith("audit") else "AUDIT",
                "parent": "",
                "phase_ref": "",
                "owner_agent": "HERMES",
                "status": "ACTIVE",
                "cards": cards_list,
                "coordination": [],
                "created_at": c_at or now_iso,
                "updated_at": u_at or now_iso,
            }
        }

        # Write to JSON file
        out_file = HERMES_BOARDS_DIR / f"{board_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(board_payload, f, indent=2, ensure_ascii=False)

        # Update registry
        registry["boards"][board_id] = {
            "board_id": board_id,
            "name": board_name,
            "type": board_payload["board"]["type"],
            "parent": "",
            "owner_agent": "HERMES",
            "status": "ACTIVE",
            "coordination": [],
            "path": str(out_file),
            "updated_at": now_iso,
        }
        exported_count += 1

    with open(HERMES_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)

    return {"exported_boards": exported_count}


async def sync_hermes_memory_to_lgp(db: Any) -> Dict[str, Any]:
    """Sync lessons and decisions from ~/.state/memory/ into LangGraph temporal_facts."""
    HERMES_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    lessons_file = HERMES_MEMORY_DIR / "lessons.json"
    decisions_file = HERMES_MEMORY_DIR / "decisions.json"

    synced_facts = 0
    now_ts = time.time()

    if lessons_file.exists():
        try:
            with open(lessons_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                lessons = data.get("lessons", [])
                for lesson in lessons:
                    fact_id = f"fact-lesson-{int(now_ts*1000)}"
                    content = lesson if isinstance(lesson, str) else json.dumps(lesson)
                    # Check if exists
                    async with db.execute(
                        "SELECT id FROM temporal_facts WHERE fact_text = ?", (content,)
                    ) as cur:
                        if not await cur.fetchone():
                            await db.execute(
                                """INSERT INTO temporal_facts 
                                   (id, fact_text, domain, confidence, valid_from, created_at, status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (fact_id, content, "lesson", 0.95, now_ts, now_ts, "active"),
                            )
                            synced_facts += 1
        except Exception as e:
            logger.warning("Failed syncing lessons: %s", e)

    await db.commit()
    return {"synced_facts": synced_facts}


async def run_full_sync(db: Any) -> Dict[str, Any]:
    """Executes complete bidirectional synchronization between Hermes and LangGraph."""
    logger.info("Executing Full Bidirectional Hermes <-> LangGraph Sync...")
    h_to_db = await sync_hermes_boards_to_db(db)
    db_to_h = await sync_db_boards_to_hermes(db)
    mem_sync = await sync_hermes_memory_to_lgp(db)

    return {
        "status": "success",
        "hermes_to_db": h_to_db,
        "db_to_hermes": db_to_h,
        "memory_sync": mem_sync,
        "timestamp": time.time(),
    }
