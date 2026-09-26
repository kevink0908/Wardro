"""
agents/wardro-stylist/agent.py — the FIRST agent: daily outfit stylist (terminal).

This is the terminal twin of host/backend.py (same agent, no web server) —
your fastest debugging harness: it tests the whole agent → MCP → Vertex chain
in one process, no uvicorn or browser needed.

History note: this began life as agent_host.py, where the hand-rolled tool-call
loop from gemini_host.py was replaced by a LangChain agent (create_agent) —
MultiServerMCPClient manages the server connections, the adapter converts MCP
tools, and the agent runs the Thought→Action→Observation loop internally.

Run (both MCP servers must already be running):
    python agents/wardro-stylist/agent.py
"""

import os
# Force gRPC to use the OS DNS resolver (fixes Vertex "Could not contact DNS
# servers" on macOS/VPN). Must run before the google/grpc imports below.
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent              # LangChain 1.0 (older tutorials: langgraph.prebuilt.create_react_agent)
from langchain_google_vertexai import ChatVertexAI      # Gemini via Vertex AI (uses your GCP credits); the deprecation warning is harmless

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION  (same values as backend.py — this is the terminal version)
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
GCP_PROJECT = "wardro-499801"
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
        "-> search_closet -> get_color_matches. Always suggest items from the user's closet."
    )

# ─────────────────────────────────────────────────────────────────────────────
# SERVER CONFIG — same two servers, described for MultiServerMCPClient.
# Today: "stdio" (the client launches each server as a subprocess, like before).
# Phase 4: swap an entry to streamable_http + a URL (commented example below).
# ─────────────────────────────────────────────────────────────────────────────
SERVERS = {
    "wardro": {
        "url": "http://127.0.0.1:8000/mcp",
        "transport": "streamable_http",
    },
    "wardrobe": {
        "url": "http://127.0.0.1:8001/mcp",
        "transport": "streamable_http",
    },
    # When deployed, change the server entry to URL:
    # Ex: "wardro": {"url": "<URL>", "transport": "streamable_http"},
    # NOTE: the client side uses "streamable_http" with an UNDERSCORE, while
    #       the server's mcp.run() used "streamable-http" with a HYPHEN.
}


def extract_text(content) -> str:
    """Return the plain text from an agent message.

    Gemini 2.5 returns message content as a LIST of parts (the visible text plus
    a 'thought_signature' reasoning blob), not a plain string. This pulls out
    just the text so it prints cleanly — and you'll reuse this exact step when
    the web backend needs to hand a clean string to the frontend.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        ).strip()
    return str(content)


async def main():
    print("Connecting to MCP servers…")

    # 1) ONE client manages connections to BOTH servers  (replaces your MCPHub).
    client = MultiServerMCPClient(SERVERS)

    # 2) get_tools() connects to every server, lists each server's MCP tools, and
    #    CONVERTS them into LangChain tool objects — all combined into ONE flat list.
    #    (This replaces your hand-written mcp_to_gemini_tools().)
    tools = await client.get_tools()
    print(f"  ✓ loaded {len(tools)} tools across all servers")

    # 3) The model — your Gemini brain, same as before.
    model = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_LOCATION)

    # 4) THE AGENT. This one call gives you the entire tool-call loop you used to
    #    hand-write. (param may be `prompt=` in some versions — check docs.)
    agent = create_agent(model, tools, system_prompt=system_prompt())

    print("\nWardro — Gemini + MCP (agent edition). 'quit' to exit.\n")

    history = []  # keep chat context across turns (LangGraph "checkpointers" = the robust way)

    while True:                                    # ← OUTER loop = the chat REPL (kept; this is the UI)
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        history.append(("user", user_input))

        # ─────────────────────────────────────────────────────────────────────
        # OLD (gemini_host.py): an inner `while True` lived here — it collected
        # function_calls, ran hub.call_tool(), fed results back, and looped until
        # Gemini returned text. ALL of that is now this ONE line; the agent runs
        # Thought → Action → Observation internally:
        # ─────────────────────────────────────────────────────────────────────
        result = await agent.ainvoke({"messages": history})

        # Extract just the text (Gemini 2.5 returns a list of content parts).
        reply = extract_text(result["messages"][-1].content)
        history.append(("assistant", reply))
        print(f"\nWardro: {reply}\n")

    print("Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
