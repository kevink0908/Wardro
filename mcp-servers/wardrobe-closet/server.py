"""
mcp-servers/wardrobe-closet/server.py — MCP server for managing your clothing inventory.

RUN:  python mcp-servers/wardrobe-closet/server.py  ->  http://127.0.0.1:8001/mcp  (hand-rolled HTTP)
CORE LOGIC: shared/wardrobe.py (this file is only the MCP "front door").

This is a SEPARATE server from wardro-weather. It manages what clothes you
actually own. The agent can use BOTH servers together:

    wardro-weather  → "What's the weather? What should I wear?"
    wardrobe-closet → "What do I actually own that matches?"

The servers never talk to each other. The agent orchestrates across them.

DATABASE: data/wardrobe.db (separate from data/wardro.db)
TOOLS: add_clothing_item, search_closet, list_all_items, remove_item,
       get_color_matches, update_item,
       log_wear, get_wear_history, get_wear_counts
"""

import sys
from pathlib import Path

# Make the project root importable so this server can use the shared/ package,
# no matter which directory you launch it from. Works on macOS and Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.mcp_server import MiniMCP     # from-scratch MCP server (no `mcp` lib)
from shared import wardrobe

mcp = MiniMCP("Wardrobe")
wardrobe.init_db()


# ---------------------------------------------------------------------------
# Tool 1: Add Clothing Item — 1 DB write
# ---------------------------------------------------------------------------
@mcp.tool()
def add_clothing_item(
    name: str,
    category: str,
    warmth_level: str,
    color: str = "",
    sleeve_type: str = "n/a",
    description: str = "",
) -> dict:
    """Add a piece of clothing to your wardrobe inventory.

    Args:
        name: What you call this item (e.g. "Blue Nike t-shirt").
        category: Type of clothing. One of: shirt, pants, shorts, jacket,
            sweater, hoodie, dress, skirt, coat, vest, accessories.
        warmth_level: How warm this item keeps you. One of: light, medium,
            heavy. Use "light" for summer clothes, "heavy" for winter coats.
        color: Primary color (e.g. "blue", "black", "red").
        sleeve_type: One of: short-sleeve, long-sleeve, sleeveless, n/a.
            Use "n/a" for pants, shorts, accessories, etc.
        description: Optional extra details (e.g. "has a hood", "formal").

    Returns:
        Confirmation with the new item's ID, or an error dict.
    """
    return wardrobe.add_item(
        name=name,
        category=category,
        warmth_level=warmth_level,
        color=color,
        sleeve_type=sleeve_type,
        description=description,
    )


# ---------------------------------------------------------------------------
# Tool 2: Search Closet — 1 DB read with optional filters
# ---------------------------------------------------------------------------
@mcp.tool()
def search_closet(
    category: str = "",
    color: str = "",
    warmth_level: str = "",
) -> list[dict]:
    """Search your wardrobe for items matching the given criteria.

    All parameters are optional filters — omit any to skip that filter.

    Args:
        category: Filter by type (e.g. "shirt", "jacket", "shorts").
        color: Filter by color (e.g. "blue", "black").
        warmth_level: Filter by warmth ("light", "medium", or "heavy").

    Returns:
        A list of matching clothing items from your inventory.
    """
    return wardrobe.search_items(
        category=category,
        color=color,
        warmth_level=warmth_level,
    )


# ---------------------------------------------------------------------------
# Tool 3: List All Items — 1 DB read, no filters
# ---------------------------------------------------------------------------
@mcp.tool()
def list_all_items() -> list[dict]:
    """List every item in your wardrobe inventory.

    Returns all clothing items sorted by category then name.
    """
    return wardrobe.list_items()


# ---------------------------------------------------------------------------
# Tool 4: Remove Item — 1 DB delete
# ---------------------------------------------------------------------------
@mcp.tool()
def remove_item(item_id: int) -> dict:
    """Remove a clothing item from your inventory by its ID.

    Use list_all_items or search_closet first to find the item's ID.

    Args:
        item_id: The numeric ID of the item to remove.

    Returns:
        Confirmation dict, or error if the item wasn't found.
    """
    return wardrobe.remove_item(item_id)


# ---------------------------------------------------------------------------
# Tool 5: Get Color Matches — pure logic, no DB
# ---------------------------------------------------------------------------
@mcp.tool()
def get_color_matches(color: str) -> dict:
    """Get a list of colors that pair well with the given color.

    Use this AFTER finding a clothing item to determine what colors
    would match for a complete outfit. For example, if you found a
    black shirt, call this with "black" to learn that gray, white,
    and navy pants would match.

    Args:
        color: The color to find matches for (e.g. "black", "navy", "khaki").

    Returns:
        A dict with the input color and its matching colors.
    """
    matches = wardrobe.get_color_matches(color)
    return {"color": color, "matches_well_with": matches}


# ---------------------------------------------------------------------------
# Tool 6: Update Item — modify fields on an existing item
# ---------------------------------------------------------------------------
@mcp.tool()
def update_item(
    item_id: int,
    name: str = "",
    category: str = "",
    warmth_level: str = "",
    color: str = "",
    sleeve_type: str = "",
    description: str = "",
    append_description: bool = False,
) -> dict:
    """Update one or more fields on an existing clothing item.

    Only provide the fields you want to change — everything else stays
    the same. Use list_all_items or search_closet first to find the ID.

    Args:
        item_id: The numeric ID of the item to update.
        name: New name (leave empty to keep current).
        category: New category (leave empty to keep current).
        warmth_level: New warmth level (leave empty to keep current).
        color: New color (leave empty to keep current).
        sleeve_type: New sleeve type (leave empty to keep current).
        description: New description text.
        append_description: If true, appends to existing description
            instead of replacing it.

    Returns:
        Confirmation dict, or error if the item wasn't found.
    """
    return wardrobe.update_item(
        item_id=item_id,
        name=name,
        category=category,
        warmth_level=warmth_level,
        color=color,
        sleeve_type=sleeve_type,
        description=description,
        append_description=append_description,
    )


# ---------------------------------------------------------------------------
# Tool 7: Log Wear — 1 DB write (record an item was worn)
# ---------------------------------------------------------------------------
@mcp.tool()
def log_wear(item_id: int, worn_on: str = "", occasion: str = "") -> dict:
    """Record that a clothing item was worn on a date.

    Call this when the user says they wore something, or after they accept
    an outfit suggestion for a specific day.

    Args:
        item_id: The wardrobe item's ID.
        worn_on: ISO date like "2026-07-08". Leave empty for today.
        occasion: Optional free-text occasion, e.g. "work", "dinner",
            "hiking", "wedding". Use the user's own words.

    Returns:
        Confirmation dict, or {"error": str} if the item doesn't exist.
    """
    return wardrobe.log_wear(item_id, worn_on, occasion)


# ---------------------------------------------------------------------------
# Tool 8: Wear History — 1 DB read (what was worn, when, for what)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_wear_history(item_id: int = 0, since: str = "", limit: int = 50) -> list[dict]:
    """List wear-log entries, newest first (item name included).

    Useful for questions like "when did I last wear the black hoodie?" or
    "what did I wear last week?".

    Args:
        item_id: Filter to one item's history. 0 = all items.
        since: Only entries on/after this ISO date (e.g. "2026-07-01").
        limit: Max entries to return.
    """
    return wardrobe.get_wear_history(item_id, since, limit)


# ---------------------------------------------------------------------------
# Tool 9: Wear Counts — 1 DB read (per-item totals, least-worn first)
# ---------------------------------------------------------------------------
@mcp.tool()
def get_wear_counts(since: str = "") -> list[dict]:
    """Per-item wear totals and last-worn date, least-worn first.

    KEY TOOL FOR PACKING: when planning a trip, prefer items worn fewer
    times recently. An item worn 2-3 times is fine to re-wear if the
    occasions differ (check get_wear_history for the occasions).

    Args:
        since: Only count wears on/after this ISO date. Empty = all time.

    Returns:
        One dict per closet item: item_id, name, category, color,
        warmth_level, times_worn, last_worn.
    """
    return wardrobe.get_wear_counts(since)


if __name__ == "__main__":
    # Same tools, two transports:
    #   python server.py          -> Streamable HTTP at http://127.0.0.1:8001/mcp  (used by host/backend.py)
    #   python server.py --stdio  -> stdio pipes  (used by Claude Desktop, which launches this script itself)
    if "--stdio" in sys.argv:
        mcp.run()
    else:
        mcp.run_http(port=8001)
