"""
host/host.py — the NO-LANGCHAIN backend variant. Hand-rolled agent, same API.

Same FastAPI endpoints as backend.py (/chat, /closet, /images, /wear-log,
/tools), same frontend, same MCP servers — but the three LangChain pieces are
replaced by code you own:

    langchain_mcp_adapters.MultiServerMCPClient  ->  mcp_client.MCPHub (urllib)
    the adapter's schema conversion              ->  mcp_to_gemini_tools()
    create_agent's internal tool-call loop       ->  run_agent_turn()'s while-loop

Third-party deps: fastapi + uvicorn (the web server) and google-genai (Gemini).
That's it — no langchain, no langgraph, no adapters, no `mcp`.

RUN (either this OR backend.py — both want port 8080):
    # terminal 1:  python mcp-servers/wardro-weather/server.py
    # terminal 2:  python mcp-servers/wardrobe-closet/server.py
    # terminal 3:  uvicorn host:app --reload --port 8080 --app-dir host

AUTH: Vertex AI Application Default Credentials, same as before
    (`gcloud auth application-default login`). No API key in code.
"""

import os
# Force gRPC to use the OS DNS resolver (fixes Vertex "Could not contact DNS
# servers" on macOS/VPN). Must run before the google imports below.
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Make BOTH the project root (for shared/) and this folder (for mcp_client.py)
# importable, regardless of where uvicorn was launched from.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import wardrobe          # closet DB, read directly for /closet & /wear-log
from mcp_client import MCPHub        # our hand-rolled MCP client (step 1)

from google import genai             # google-genai SDK — the ONLY AI dependency
from google.genai import types

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — identical to backend.py
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
GCP_PROJECT = "wardro-499620"
GCP_LOCATION = "us-central1"

SERVERS = {
    "wardro":   "http://127.0.0.1:8000/mcp",
    "wardrobe": "http://127.0.0.1:8001/mcp",
}


def system_prompt() -> str:
    """Built fresh so the agent knows TODAY's date (LLMs can't guess 'tomorrow')."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    return (
        f"You are Wardro, a personal styling assistant. Today is {today}. "
        "Resolve relative dates like 'tomorrow' or 'this weekend' from that date "
        "before calling get_forecast. "
        "For outfit questions: geocode -> get_weather/get_forecast -> outfit_advice "
        "-> search_closet -> get_color_matches. Always suggest items from the user's closet. "
        "Prefer items worn less recently/often (check get_wear_counts) so outfits rotate. "
        "When the user says they wore something — or accepts an outfit for a specific "
        "day — call log_wear for each item (pass the occasion in the user's own words). "
        "For 'when did I last wear X?' use get_wear_history."
    )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — SCHEMA CONVERSION: MCP tool dicts -> Gemini function declarations.
# (Same idea as mcp_to_gemini_tools in _archive/gemini_host.py, but reading the
# plain dicts our hand-rolled client returns instead of `mcp` SDK objects.)
# MCP and Gemini both describe params with JSON Schema; Gemini just wants its
# own Schema objects and only a subset of the keywords.
# ─────────────────────────────────────────────────────────────────────────────
TYPE_MAP = {
    "string": "STRING", "number": "NUMBER", "integer": "INTEGER",
    "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT",
}


def mcp_to_gemini_tools(tools: list[dict]) -> list[types.Tool]:
    """[{name, description, inputSchema}] -> one Gemini Tool with N declarations."""
    declarations = []
    for tool in tools:
        schema = tool.get("inputSchema") or {}
        props = {
            pname: types.Schema(
                type=TYPE_MAP.get(pdef.get("type", "string"), "STRING"),
                description=pdef.get("description", ""),
            )
            for pname, pdef in (schema.get("properties") or {}).items()
        }
        declarations.append(types.FunctionDeclaration(
            name=tool["name"],
            description=(tool.get("description") or "")[:1024],
            parameters=types.Schema(
                type="OBJECT", properties=props,
                required=schema.get("required", []),
            ) if props else None,
        ))
    return [types.Tool(function_declarations=declarations)]


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — THE AGENT LOOP (what create_agent did): send the message, and while
# Gemini answers with function CALLS instead of text, execute them over MCP and
# feed the results back. Text answer = loop over.
# ─────────────────────────────────────────────────────────────────────────────
def run_agent_turn(chat, hub: MCPHub, message) -> str:
    """One user turn: message in -> (tool calls...) -> final text out."""
    response = chat.send_message(message)

    while True:
        # 1. Did Gemini ask to CALL functions, or did it ANSWER with text?
        fn_calls = []
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts or []:
                if part.function_call and part.function_call.name:
                    fn_calls.append(part.function_call)
        if not fn_calls:
            break                                   # text answer -> done

        # 2. Execute every requested call via our MCP client.
        fn_response_parts = []
        for fc in fn_calls:
            args = dict(fc.args) if fc.args else {}
            print(f"  🔧 {fc.name}({json.dumps(args, default=str)})")
            result = hub.call_tool(fc.name, args)   # routed to the right server
            fn_response_parts.append(types.Part.from_function_response(
                name=fc.name, response={"result": result},
            ))

        # 3. Feed ALL results back in one message; Gemini continues reasoning.
        response = chat.send_message(fn_response_parts)

    try:
        return response.text or "(no text in response)"
    except (ValueError, AttributeError):
        return "(Gemini returned no text response)"


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI APP — everything below matches backend.py's surface exactly
# ─────────────────────────────────────────────────────────────────────────────
STATE = {"hub": None, "chat": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Connecting to MCP servers (hand-rolled client)…")
    hub = MCPHub(SERVERS)
    hub.connect_all()

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    # client.chats.create keeps the conversation HISTORY for us — the SDK
    # equivalent of the HISTORY list in backend.py. Single-user for now.
    STATE["chat"] = client.chats.create(
        model=GEMINI_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt(),
            tools=mcp_to_gemini_tools(hub.tools),
        ),
    )
    STATE["hub"] = hub
    print(f"  ✓ agent ready with {len(hub.tools)} tools — open http://localhost:8080/docs")
    yield


app = FastAPI(title="Wardro API (no-LangChain variant)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten to the real frontend URL before deploying
    allow_methods=["*"],
    allow_headers=["*"],
)

wardrobe.init_db()  # makes sure data/wardrobe_images exists before mounting it
app.mount("/images", StaticFiles(directory=wardrobe.IMAGE_DIR), name="images")


@app.get("/closet")
def closet():
    """Every clothing item, each with an image URL the browser can load."""
    items = wardrobe.list_items()
    for it in items:
        p = it.get("image_path") or ""
        it["image_url"] = f"http://localhost:8080/images/{os.path.basename(p)}" if p else None
    return {"items": items}


@app.get("/wear-log")
def wear_log():
    """Recent wear entries + per-item totals (read straight from the DB)."""
    return {
        "entries": wardrobe.get_wear_history(limit=100),
        "counts": wardrobe.get_wear_counts(),
    }


@app.get("/tools")
def tools():
    """Every MCP tool the host discovered, across ALL servers."""
    hub = STATE["hub"]
    return {
        "count": len(hub.tools) if hub else 0,
        "tools": [
            {"server": t["server"], "name": t["name"],
             "description": (t.get("description") or "").split("\n")[0]}
            for t in (hub.tools if hub else [])
        ],
    }


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
def root():
    return {"status": "Wardro backend (no-LangChain) running — open /docs to try it"}


# NOTE: a plain `def` (not `async def`) is deliberate. Our MCP client (urllib)
# and the genai SDK are synchronous; FastAPI runs sync endpoints in a thread
# pool so the server stays responsive while a turn is in flight.
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Send a message to the hand-rolled agent and get its reply."""
    reply = run_agent_turn(STATE["chat"], STATE["hub"], req.message)
    return ChatResponse(reply=reply)
