# Connecting Wardro to an Agent (Claude Desktop) via MCP

Goal: chat with Claude Desktop and have it call **your** Wardro tools — which hit
the weather APIs and read/write your SQLite database. No API key needed: Claude
Desktop is the LLM doing the tool-calling.

> **One rule before anything else:** the MCP server file (`wardro_mcp.py`) and the
> Python that runs it must live on the **same computer as Claude Desktop**, and
> that Python must have `gradio`, `requests`, and `mcp` installed. MCP launches
> your script locally and talks to it over a pipe.

---

## Step 1 — Install the dependencies in a virtual environment

`mcp` requires Python **3.10+**. The cleanest way to guarantee one consistent
interpreter (and avoid the "packages installed in the wrong Python" trap) is a
**virtual environment** — a self-contained folder where `python` and `pip`
always mean the same thing.

```bash
cd /Users/kevink0908/Desktop/Projects/Python/Wardro
python3 --version                 # make sure this is 3.10 or higher
python3 -m venv .venv             # create the env (one time only)
source .venv/bin/activate         # macOS/Linux — your prompt shows (.venv)
# Windows PowerShell instead:  .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt   # installs requests, gradio, AND mcp here
```

Each new terminal: `cd` into the folder and run the `activate` line again before
starting the app or the server.

> If `python3 --version` is below 3.10, install a newer one first
> (`brew install python@3.12` on macOS) and use that to create the venv.

## Step 2 — Find the venv's Python path

Claude Desktop needs the **absolute path** to the venv's Python. With the venv
active, run:

- macOS/Linux: `which python`  → e.g. `/Users/kevink0908/Desktop/Projects/Python/Wardro/.venv/bin/python`
- Windows: `where python`  → e.g. `C:\Users\kimke8\Desktop\Wardro\.venv\Scripts\python.exe`

Write down whatever it prints — you'll paste it in Step 4.

## Step 3 — Sanity-check the server starts

```bash
python3 wardro_mcp.py
```

It should print nothing and just **hang** — that's correct. An MCP server waits
silently for a client to connect. Press `Ctrl+C` to stop. If instead you get an
error like `ModuleNotFoundError: No module named 'mcp'`, redo Step 1 for the
right Python.

## Step 4 — Tell Claude Desktop about the server

1. Open **Claude Desktop → Settings → Developer → Edit Config**. This opens a
   file called `claude_desktop_config.json` in your text editor.
   (If the button isn't there, edit the file directly — locations below.)

2. Paste this, replacing the two paths with **your** Python path (Step 2) and
   **your** absolute path to `wardro_mcp.py`:

   **macOS example** (note: the venv's Python, from Step 2):
   ```json
   {
     "mcpServers": {
       "wardro": {
         "command": "/Users/kevink0908/Desktop/Projects/Python/Wardro/.venv/bin/python",
         "args": ["/Users/kevink0908/Desktop/Projects/Python/Wardro/wardro_mcp.py"]
       }
     }
   }
   ```

   **Windows example** (note the doubled backslashes):
   ```json
   {
     "mcpServers": {
       "wardro": {
         "command": "C:\\Users\\kimke8\\Desktop\\Wardro\\.venv\\Scripts\\python.exe",
         "args": ["C:\\Users\\kimke8\\Desktop\\Wardro\\wardro_mcp.py"]
       }
     }
   }
   ```

   Using the venv's Python here is what guarantees Claude Desktop runs the server
   with `gradio`/`requests`/`mcp` available — no "ModuleNotFoundError".

   If the file already has other servers under `"mcpServers"`, just add the
   `"wardro": { ... }` block alongside them (don't create a second
   `"mcpServers"` key). The whole file must stay valid JSON.

3. Save the file.

### Where the config file lives (for reference)
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

## Step 5 — Fully restart Claude Desktop

Quit completely (on macOS, `Cmd+Q` — not just closing the window) and reopen it.
MCP servers are only picked up at startup.

## Step 6 — Verify the tools are there

In a new chat, look for the tools/connector icon (a small slider or plug icon
near the message box). Click it and you should see **Wardro** with two tools:
`get_outfit_recommendation` and `get_search_history`.

## Step 7 — Try it (this is the demo for your mentor)

Ask Claude Desktop, in plain English:

1. **"What should I wear in Austin, TX today?"**
   → Claude calls `get_outfit_recommendation("Austin, TX", by="City + State")`.
   It will ask your permission to run the tool the first time — click Allow.

2. **"Check zip code 95127 and tell me what to wear."**
   → Claude calls the same tool with `by="Zip code"`. (Notice the agent figured
   out which mode to use from your wording — that's the LLM choosing arguments.)

3. **"What locations have I looked up recently?"**
   → Claude calls `get_search_history()`, which reads your SQLite database.
   This proves the agent is using the DB, not just the APIs.

Each tool call shows up expandable in the chat, so you can show your mentor the
exact arguments Claude chose and the raw result your code returned.

---

## Troubleshooting

- **Wardro doesn't appear in the tools list.** Almost always the config: the
  `command` path isn't the Python that has the packages, or the `args` path to
  `wardro_mcp.py` is wrong, or the JSON is invalid (a stray comma). Paste the
  file into a JSON validator if unsure.
- **It appears but errors when called.** Open **Settings → Developer** and view
  the MCP logs (macOS log files live in
  `~/Library/Logs/Claude/mcp-server-wardro.log`). A `ModuleNotFoundError` there
  means the `command` Python is missing `gradio`/`requests`/`mcp` — redo Step 1
  for *that* Python.
- **`spawn ... ENOENT`** in the logs means the `command` path is wrong — Python
  isn't at that location. Re-run Step 2.
- **Changes to `wardro_mcp.py` don't show up.** Restart Claude Desktop; it only
  reloads servers on startup.

## How this maps to the concepts

- **Agent** = Claude Desktop (the LLM running the decide → call → read loop).
- **Tools** = your `@mcp.tool()` functions.
- **MCP** = the standard that lets the agent discover and call those tools.
- **Your APIs + DB** = what the tools actually do when called.

Same core functions as the Gradio app — MCP is just a second front door that
puts an agent in the driver's seat instead of a web form.
