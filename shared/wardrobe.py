"""
wardrobe.py — Core logic for managing your clothing inventory.

This module is the "one source of truth" for wardrobe operations, just like
wardro_core.py is for weather. Two front doors use it:
   1. mcp-servers/wardrobe-closet/server.py — MCP server (agent access)
   2. host/backend.py                       — FastAPI backend (/closet + image serving)

DATABASE: data/wardrobe.db (separate from data/wardro.db)
IMAGES:   data/wardrobe_images/ folder

PORTABILITY NOTE: image_path is stored in the DB as a FILENAME only
(e.g. "item_42.png"), never an absolute path, so the database can be copied
between machines (macOS <-> Windows) without breaking. Paths are resolved
against IMAGE_DIR at read time (see _auto_discover_image).
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "wardrobe.db"
IMAGE_DIR = DATA_DIR / "wardrobe_images"


# ---------------------------------------------------------------------------
# VALID VALUES (used for validation and Gradio dropdowns)
# ---------------------------------------------------------------------------
CATEGORIES = [
    "shirt", "pants", "shorts", "jacket", "sweater", "hoodie",
    "dress", "shoes", "coat", "vest", "accessories",
]

SLEEVE_TYPES = ["short-sleeve", "long-sleeve", "sleeveless", "n/a"]

WARMTH_LEVELS = ["light", "medium", "heavy"]


# ---------------------------------------------------------------------------
# COLOR MATCHING RULES
# ---------------------------------------------------------------------------
# Each key maps to a list of colors that pair well with it.
# These are Kevin's rules + common menswear guidelines.
COLOR_MATCHES = {
    "black":      ["gray", "white", "navy", "red", "light blue"],
    "gray":       ["black", "white", "navy", "blue", "pink"],
    "white":      ["black", "gray", "navy", "brown", "blue", "khaki", "red"],
    "navy":       ["gray", "white", "khaki", "light blue", "brown"],
    "blue":       ["gray", "white", "black", "khaki", "brown"],
    "light blue": ["navy", "white", "gray", "khaki", "brown"],
    "red":        ["black", "white", "gray", "navy"],
    "green":      ["black", "white", "khaki", "brown", "gray"],
    "brown":      ["white", "khaki", "light blue", "navy", "gray"],
    "khaki":      ["navy", "white", "blue", "light blue", "brown", "black"],
    "pink":       ["gray", "navy", "white", "black"],
    "olive":      ["white", "khaki", "black", "brown", "gray"],
    "burgundy":   ["gray", "white", "black", "khaki", "navy"],
    "cream":      ["navy", "brown", "black", "olive", "burgundy"],
}


# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------
def init_db():
    """Create the 'items' and 'wear_log' tables if they don't exist.

    Also creates the wardrobe_images/ folder for storing photos.
    """
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            sleeve_type  TEXT    DEFAULT 'n/a',
            color        TEXT,
            warmth_level TEXT    NOT NULL,
            description  TEXT,
            image_path   TEXT,
            added_at     TEXT    NOT NULL
        )
        """
    )
    # One row per time an item is worn. 'occasion' is deliberately just free
    # text (not a table or enum) — the agent decides what counts as an
    # occasion ("work", "dinner", "hiking"). Data stays simple; smarts live
    # in the agent.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wear_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id  INTEGER NOT NULL REFERENCES items(id),
            worn_on  TEXT    NOT NULL,          -- ISO date "2026-07-08"
            occasion TEXT    DEFAULT ''         -- free text, optional
        )
        """
    )
    conn.commit()
    conn.close()


def add_item(
    name: str,
    category: str,
    warmth_level: str,
    color: str = "",
    sleeve_type: str = "n/a",
    description: str = "",
    image_source_path: str = "",
) -> dict:
    """Add a clothing item to the database. Optionally copies an image.

    Args:
        image_source_path: If provided, the image is copied into
            wardrobe_images/ and the new path is stored in the DB.

    Returns:
        {"status": "added", "item_id": int, "name": str} on success,
        {"error": str} on validation failure.
    """
    category = category.lower().strip()
    warmth_level = warmth_level.lower().strip()
    sleeve_type = sleeve_type.lower().strip()

    if category not in CATEGORIES:
        return {"error": f"Unknown category '{category}'. Valid: {CATEGORIES}"}
    if warmth_level not in WARMTH_LEVELS:
        return {"error": f"Unknown warmth_level '{warmth_level}'. Valid: {WARMTH_LEVELS}"}
    if sleeve_type not in SLEEVE_TYPES:
        return {"error": f"Unknown sleeve_type '{sleeve_type}'. Valid: {SLEEVE_TYPES}"}

    # Save image if provided
    saved_image = ""
    if image_source_path:
        src = Path(image_source_path)
        if src.is_file():
            # We'll rename after we have the item_id, so save to a temp name first
            saved_image = str(src)  # placeholder, updated below

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """INSERT INTO items (name, category, sleeve_type, color,
                              warmth_level, description, image_path, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name.strip(),
            category,
            sleeve_type,
            color.lower().strip(),
            warmth_level,
            description.strip(),
            "",  # will update after we have the id
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    item_id = cursor.lastrowid

    # Now copy the image with a stable name: item_42.jpg
    if image_source_path:
        src = Path(image_source_path)
        if src.is_file():
            dest = IMAGE_DIR / f"item_{item_id}{src.suffix}"
            shutil.copy2(src, dest)
            conn.execute(
                "UPDATE items SET image_path = ? WHERE id = ?",
                (dest.name, item_id),  # store FILENAME only (portable across machines)
            )

    conn.commit()
    conn.close()
    return {"status": "added", "item_id": item_id, "name": name}


def search_items(
    category: str = "",
    color: str = "",
    warmth_level: str = "",
) -> list[dict]:
    """Search the wardrobe with optional filters. Returns list of dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conditions, params = [], []
    if category:
        conditions.append("category = ?")
        params.append(category.lower().strip())
    if color:
        conditions.append("color = ?")
        params.append(color.lower().strip())
    if warmth_level:
        conditions.append("warmth_level = ?")
        params.append(warmth_level.lower().strip())

    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM items WHERE {where} ORDER BY id ASC",
        params,
    ).fetchall()
    conn.close()
    items = [dict(row) for row in rows]
    for item in items:
        item["image_path"] = _auto_discover_image(item["id"], item.get("image_path", ""))
    return items


def list_items() -> list[dict]:
    """Return every item in the wardrobe."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM items ORDER BY id ASC"
    ).fetchall()
    conn.close()
    items = [dict(row) for row in rows]
    for item in items:
        item["image_path"] = _auto_discover_image(item["id"], item.get("image_path", ""))
    return items


def remove_item(item_id: int) -> dict:
    """Delete an item by ID. Also removes its image file if present."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT image_path FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": f"No item found with id {item_id}"}

    # Delete image file if it exists
    if row["image_path"]:
        img = Path(row["image_path"])
        if not img.is_absolute():
            img = IMAGE_DIR / img  # stored as a filename — resolve it
        if img.is_file():
            img.unlink()

    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"status": "removed", "item_id": item_id}


def update_item(
    item_id: int,
    name: str = "",
    category: str = "",
    warmth_level: str = "",
    color: str = "",
    sleeve_type: str = "",
    description: str = "",
    image_source_path: str = "",
    append_description: bool = False,
) -> dict:
    """Update fields on an existing item. Only non-empty fields are changed.

    Args:
        item_id: The ID of the item to update.
        append_description: If True, the description is appended to the
            existing one instead of replacing it.
        image_source_path: If provided, copies the new image into
            wardrobe_images/ (replacing the old one if present).

    Returns:
        {"status": "updated", "item_id": int} on success,
        {"error": str} on failure.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": f"No item found with id {item_id}"}

    updates, params = [], []

    if name:
        updates.append("name = ?")
        params.append(name.strip())
    if category:
        cat = category.lower().strip()
        if cat not in CATEGORIES:
            conn.close()
            return {"error": f"Unknown category '{cat}'. Valid: {CATEGORIES}"}
        updates.append("category = ?")
        params.append(cat)
    if warmth_level:
        wl = warmth_level.lower().strip()
        if wl not in WARMTH_LEVELS:
            conn.close()
            return {"error": f"Unknown warmth_level '{wl}'. Valid: {WARMTH_LEVELS}"}
        updates.append("warmth_level = ?")
        params.append(wl)
    if color:
        updates.append("color = ?")
        params.append(color.lower().strip())
    if sleeve_type:
        st = sleeve_type.lower().strip()
        if st not in SLEEVE_TYPES:
            conn.close()
            return {"error": f"Unknown sleeve_type '{st}'. Valid: {SLEEVE_TYPES}"}
        updates.append("sleeve_type = ?")
        params.append(st)
    if description:
        if append_description and row["description"]:
            new_desc = row["description"] + "; " + description.strip()
        else:
            new_desc = description.strip()
        updates.append("description = ?")
        params.append(new_desc)

    # Handle image
    if image_source_path:
        src = Path(image_source_path)
        if src.is_file():
            # Remove old image if it exists
            if row["image_path"]:
                old = Path(row["image_path"])
                if old.is_file():
                    old.unlink()
            dest = IMAGE_DIR / f"item_{item_id}{src.suffix}"
            shutil.copy2(src, dest)
            updates.append("image_path = ?")
            params.append(dest.name)  # store FILENAME only (portable across machines)

    if not updates:
        conn.close()
        return {"error": "Nothing to update — all fields were empty."}

    params.append(item_id)
    conn.execute(
        f"UPDATE items SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()
    return {"status": "updated", "item_id": item_id}


def _auto_discover_image(item_id: int, current_path: str) -> str:
    """If image_path is empty or the file is missing, look for item_{id}.* in wardrobe_images/.

    This lets images 'just work' when you drop a file named item_42.jpg
    into wardrobe_images/ — no DB update needed.
    """
    if current_path:
        p = Path(current_path)
        if not p.is_absolute():
            p = IMAGE_DIR / p  # stored as a filename — resolve against IMAGE_DIR
        if p.is_file():
            return str(p)
    # Search for any file matching the pattern (also rescues stale absolute
    # paths left over from another machine, since files are named item_{id}.*)
    for f in IMAGE_DIR.glob(f"item_{item_id}.*"):
        if f.is_file():
            return str(f)
    return current_path  # unchanged (empty or stale)


def get_item(item_id: int) -> dict | None:
    """Fetch a single item by ID. Returns dict or None."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["image_path"] = _auto_discover_image(item_id, item.get("image_path", ""))
    return item


# ---------------------------------------------------------------------------
# WEAR LOG — track what was worn, when, and (optionally) for what occasion
# ---------------------------------------------------------------------------
def log_wear(item_id: int, worn_on: str = "", occasion: str = "") -> dict:
    """Record that an item was worn on a date.

    Args:
        item_id: The clothing item's ID.
        worn_on: ISO date "2026-07-08". Empty = today.
        occasion: Optional free text ("work", "dinner", "hiking").

    Returns:
        {"status": "logged", ...} or {"error": ...}.
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": f"No item found with id {item_id}"}

    worn_on = worn_on.strip() or datetime.now().date().isoformat()
    try:
        datetime.fromisoformat(worn_on)  # validate the date format
    except ValueError:
        conn.close()
        return {"error": f"Invalid date '{worn_on}'. Use ISO format like 2026-07-08."}

    conn.execute(
        "INSERT INTO wear_log (item_id, worn_on, occasion) VALUES (?, ?, ?)",
        (item_id, worn_on, occasion.strip()),
    )
    conn.commit()
    conn.close()
    return {"status": "logged", "item_id": item_id, "name": row[0],
            "worn_on": worn_on, "occasion": occasion.strip()}


def get_wear_history(item_id: int = 0, since: str = "", limit: int = 50) -> list[dict]:
    """List wear-log entries, newest first, with item names joined in.

    Args:
        item_id: Filter to one item. 0 = all items.
        since: Only entries on/after this ISO date. Empty = no date filter.
        limit: Max rows returned.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conditions, params = [], []
    if item_id:
        conditions.append("w.item_id = ?")
        params.append(item_id)
    if since:
        conditions.append("w.worn_on >= ?")
        params.append(since)
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"""SELECT w.id, w.item_id, i.name, w.worn_on, w.occasion
            FROM wear_log w JOIN items i ON i.id = w.item_id
            WHERE {where}
            ORDER BY w.worn_on DESC, w.id DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_wear_counts(since: str = "") -> list[dict]:
    """How many times each item has been worn (0 included), least-worn first.

    The trip-planner agent uses this to avoid over-packing the same items:
    'suggest the charcoal sweater — it's only been worn once this month.'

    Args:
        since: Only count wears on/after this ISO date. Empty = all time.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    date_filter = "AND w.worn_on >= ?" if since else ""
    params = [since] if since else []
    rows = conn.execute(
        f"""SELECT i.id AS item_id, i.name, i.category, i.color, i.warmth_level,
                   COUNT(w.id) AS times_worn, MAX(w.worn_on) AS last_worn
            FROM items i
            LEFT JOIN wear_log w ON w.item_id = i.id {date_filter}
            GROUP BY i.id
            ORDER BY times_worn ASC, i.id ASC""",
        params,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# COLOR MATCHING
# ---------------------------------------------------------------------------
def get_color_matches(color: str) -> list[str]:
    """Return a list of colors that pair well with the given color.

    If the color isn't in our rules, returns a safe default list.
    """
    color = color.lower().strip()
    if color in COLOR_MATCHES:
        return COLOR_MATCHES[color]
    # Fallback: neutrals go with everything
    return ["black", "gray", "white", "navy"]


# ---------------------------------------------------------------------------
# GRADIO HELPERS
# ---------------------------------------------------------------------------
def load_closet_table() -> list[list]:
    """Format wardrobe items for a Gradio Dataframe (list of lists)."""
    items = list_items()
    return [
        [
            i["id"],
            i["name"],
            i["category"],
            i["sleeve_type"],
            i["color"],
            i["warmth_level"],
            i["description"] or "",
        ]
        for i in items
    ]


def load_closet_gallery() -> list[tuple]:
    """Return (image_path, caption) tuples for Gradio Gallery."""
    items = list_items()
    gallery = []
    for i in items:
        if i["image_path"] and Path(i["image_path"]).is_file():
            caption = f"{i['name']} ({i['color']} {i['category']})"
            gallery.append((i["image_path"], caption))
    return gallery
