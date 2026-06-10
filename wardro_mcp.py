"""
wardro_mcp.py — exposes Wardro's functions as MCP TOOLS an agent can call.

WHAT IS MCP (read this — it's the whole point of this file):

MCP = Model Context Protocol. It's a standard "plug" that lets an LLM (the
agent — here, Claude Desktop) discover and call functions you wrote. You don't
write any AI code. You just:

   1. Mark a few plain Python functions as @mcp.tool().
   2. Run this file as an MCP "server".
   3. Tell Claude Desktop about it (one config entry — see MCP_SETUP.md).

After that, when you chat with Claude and ask "what should I wear in Austin?",
Claude SEES your tools, decides to call get_outfit_recommendation("Austin, TX"),
your code runs (hitting the weather APIs + saving to SQLite), the result goes
back to Claude, and Claude answers you in plain English. That decide-call-read
loop IS "an agent using tools."

HOW THIS CONNECTS TO EVERYTHING YOU BUILT:
   - Tool #1 runs your API chain (geocode -> weather -> advice) AND writes a row
     to the database. So one tool demonstrates APIs + chaining + DB write.
   - Tool #2 reads from the database. So the agent is using the DB directly.

We REUSE the exact functions from Wardro.py rather than rewriting them — one
source of truth. The Gradio UI and this MCP server are just two different
"front doors" onto the same core logic.

Run it directly to sanity-check it starts:   python wardro_mcp.py
(It will wait silently for a client to connect — that's expected. Ctrl+C to stop.)
"""

from mcp.server.fastmcp import FastMCP

# Import the functions we already wrote and tested in the Gradio app.
# Because this file lives in the same folder as Wardro.py, `import Wardro`
# works no matter what directory Claude Desktop launches us from.
import Wardro

# Create the server. The name "Wardro" is what shows up in Claude's tool list.
mcp = FastMCP("Wardro")

# Make sure the database table exists before any tool tries to use it.
Wardro.init_db()


@mcp.tool()
def get_outfit_recommendation(location: str, by: str = "City + State") -> str:
    """Get a weather-based outfit recommendation for a US location.

    This runs the full chain — geocode the location to coordinates, fetch the
    current weather, turn the temperature into outfit advice — and saves the
    lookup to Wardro's database.

    Args:
        location: A US city (optionally with state, e.g. "Austin, TX") when
            `by` is "City + State", OR a US ZIP code (e.g. "78701") when
            `by` is "Zip code".
        by: How to interpret `location`. Either "City + State" or "Zip code".

    Returns:
        A short Markdown report with the location, current temperature, and
        what to wear.
    """
    return Wardro.recommend(location, by)


@mcp.tool()
def get_search_history(limit: int = 10) -> list[dict]:
    """Return the most recent outfit lookups saved in Wardro's database.

    Reads straight from the SQLite database, newest first. Use this to answer
    questions like "what places have I checked recently?".

    Args:
        limit: How many recent lookups to return (default 10).

    Returns:
        A list of rows, each with: searched_at, location, temp_f, advice.
    """
    rows = Wardro.get_history(limit)
    # rows are sqlite3.Row objects; convert to plain dicts so MCP can serialize
    # them to JSON for the agent.
    return [dict(row) for row in rows]


if __name__ == "__main__":
    # mcp.run() starts the server and speaks the MCP protocol over stdio
    # (standard input/output). Claude Desktop launches this file and talks to it
    # through that pipe — which is why no network port or API key is needed.
    mcp.run()
