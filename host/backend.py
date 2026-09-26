"""
host/backend.py — Wardro web backend (FastAPI) = the MCP HOST.

Puts an HTTP "front door" on the LangChain agent so the web frontend can talk
to it. This is the only component that talks to BOTH MCP servers.

PORTS:
    8000  → wardro-weather  MCP server  (python mcp-servers/wardro-weather/server.py)
    8001  → wardrobe-closet MCP server  (python mcp-servers/wardrobe-closet/server.py)
    8080  → THIS FastAPI backend  (/chat, /closet, /images, /docs)
    3000  → Next.js frontend      (npm run dev, in frontend/)

HOW TO RUN (from the project root):
    # terminal 1:  python mcp-servers/wardro-weather/server.py    (HTTP :8000)
    # terminal 2:  python mcp-servers/wardrobe-closet/server.py   (HTTP :8001)
    # terminal 3:  uvicorn backend:app --reload --port 8080 --app-dir host
Then open the auto-generated, clickable API docs:
    http://localhost:8080/docs        ← NOTE: 8080, not 8000 (8000 is the MCP server)
"""

import os
# Force gRPC to use the operating system's DNS resolver. Without this, the
# Vertex/gRPC client's bundled resolver can fail on macOS (especially on VPNs or
# some networks) with "Could not contact DNS servers". MUST run before the
# google/grpc libraries are imported below. (Baked in so you don't have to set
# GRPC_DNS_RESOLVER=native in the terminal every time.)
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import sys
from contextlib import asynccontextmanager

from pathlib import Path

# Make the project root importable so the backend can use the shared/ package,
# no matter which directory you launch it from. Works on macOS and Windows.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared import wardrobe  # closet DB module — the backend reads the closet directly from it

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain.agents.middleware import ModelFallbackMiddleware, ModelRetryMiddleware
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI  # Gemini API (AI Studio key) — no GCP billing needed

load_dotenv(PROJECT_ROOT / ".env")   # reads GEMINI_API_KEY from the project-root .env

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — mirrors agent_host.py (same agent, same servers)
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GCP_PROJECT = "wardro-499620"
GCP_LOCATION = "us-central1"

def system_prompt() -> str:
    """Built fresh (not a constant) so the agent always knows TODAY's date.

    Without this, the LLM guesses what 'tomorrow' means from its training data
    and calls get_forecast with a date outside Open-Meteo's 7-day window.
    """
    from datetime import datetime
    today = datetime.now().strftime("%A, %B %d, %Y")
    return (
        f"You are Wardro, a personal styling assistant. Today is {today}. "
        "Resolve relative dates like 'tomorrow' or 'this weekend' from that date "
        "before calling get_forecast. "
        "For outfit questions: geocode -> get_weather/get_forecast -> outfit_advice "
        "-> search_closet -> get_color_matches. Always suggest items from the user's closet. "
        "Prefer items worn less recently/often (check get_wear_counts) so outfits rotate. "
        "When the user says they wore something — or accepts an outfit for a specific "
        "day — call log_wear for each item (pass the occasion in the user's own words, "
        "e.g. 'work', 'dinner'). For 'when did I last wear X?' use get_wear_history."
    )

SERVERS = {
    # Both servers speak MCP BY HAND over Streamable HTTP (shared/mcp_server.py's
    # hand-rolled HTTP transport — no FastMCP). You run each server yourself and
    # the host connects to its URL — which is what makes them reachable remotely.
    "wardro":   {"url": "http://127.0.0.1:8000/mcp", "transport": "streamable_http"},
    "wardrobe": {"url": "http://127.0.0.1:8001/mcp", "transport": "streamable_http"},
}


def extract_text(content) -> str:
    """Gemini 2.5 returns content as a LIST of parts; return just the text string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict)).strip()
    return str(content)


# The agent is built ONCE at startup and reused for every request (not per call).
AGENT = {"runnable": None}
HISTORY = []  # simple single-user memory for now; per-user sessions come in Milestone 4


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server boots: connect to the MCP servers + build the agent.
    # (This is the same code as agent_host.main(), minus the terminal chat loop.)
    print("Connecting to MCP servers…")
    client = MultiServerMCPClient(SERVERS)
    tools = await client.get_tools()                       # MCP tools -> LangChain tools
    # Remember the combined tool list so GET /tools can show everything the
    # host sees across ALL servers (Inspector can only show one server at a time).
    AGENT["tools"] = [
        {"name": t.name, "description": (t.description or "").split("\n")[0]}
        for t in tools
    ]
    # Was: ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_LOCATION)
    model = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=os.environ["GEMINI_API_KEY"])
    # Gemini's free tier sometimes returns 503 "high demand". If the main model
    # fails, try lighter models; if all of them fail, wait and try again.
    backups = [
        ChatGoogleGenerativeAI(model=m, google_api_key=os.environ["GEMINI_API_KEY"])
        for m in ("gemini-flash-lite-latest", "gemini-2.5-flash")
    ]
    AGENT["runnable"] = create_agent(
        model, tools, system_prompt=system_prompt(),
        middleware=[
            ModelRetryMiddleware(max_retries=3, initial_delay=2.0, on_failure="error"),
            ModelFallbackMiddleware(*backups),
        ],
    )
    print(f"  ✓ agent ready with {len(tools)} tools — open http://localhost:8080/docs")
    yield
    # (nothing to clean up for now)


app = FastAPI(title="Wardro API", lifespan=lifespan)

# Let the React dev server (http://localhost:3000) call this API in Milestone 2.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten to your real frontend URL before deploying
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Closet: serve the wardrobe photos as static files + a JSON list of items.
# The web app reads the closet DB directly (via wardrobe.py) — no MCP needed for
# reads, since the host and the app are now combined into one backend.
wardrobe.init_db()  # makes sure data/wardrobe_images exists before mounting it
app.mount("/images", StaticFiles(directory=wardrobe.IMAGE_DIR), name="images")


@app.get("/closet")
def closet():
    """Return every clothing item, each with an image URL the browser can load."""
    items = wardrobe.list_items()
    for it in items:
        p = it.get("image_path") or ""
        it["image_url"] = f"http://localhost:8080/images/{os.path.basename(p)}" if p else None
    return {"items": items}


@app.get("/wear-log")
def wear_log():
    """The wear log for the web app: recent entries + per-item totals.

    Like /closet, this reads the DB directly via shared/wardrobe.py — no MCP
    round-trip needed for a plain page view. (The agent writes entries through
    the wardrobe-closet server's log_wear tool; both paths hit the same table.)
    """
    return {
        "entries": wardrobe.get_wear_history(limit=100),
        "counts": wardrobe.get_wear_counts(),
    }


@app.get("/tools")
def tools():
    """Every MCP tool the host discovered across ALL servers at startup.

    Handy for demos: Inspector connects to one server at a time, but this is
    the combined toolbox the agent actually reasons over.
    """
    return {"count": len(AGENT.get("tools") or []), "tools": AGENT.get("tools") or []}


# Request/response shapes. FastAPI uses these to validate input and to
# auto-generate the interactive /docs page.
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
def root():
    return {"status": "Wardro backend running — open /docs to try it"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message to the Wardro agent and get its reply."""
    HISTORY.append(("user", req.message))
    result = await AGENT["runnable"].ainvoke({"messages": HISTORY})   # agent runs the whole tool loop
    reply = extract_text(result["messages"][-1].content)             # clean text for the frontend
    HISTORY.append(("assistant", reply))
    return ChatResponse(reply=reply)
