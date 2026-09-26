"""
agents/trip-planner/agent.py — a SECOND agent: multi-day trip packing planner.

Wardro (host/) answers "what should I wear TODAY?". This agent answers
"what should I PACK for a 4-day trip?" — a different job, so it gets its
own folder, its own system prompt, and its own process (one agent per folder).

It reuses the SAME two MCP servers — no new tools were written for this agent;
it just orchestrates the existing ones differently:

    wardro-weather   → geocode, get_forecast (one call per trip day)
    wardrobe-closet  → get_wear_counts, get_wear_history, search_closet,
                       get_color_matches, log_wear

Packing logic lives entirely in the SYSTEM PROMPT, not in code. Notably,
"occasions" are not a feature anywhere — occasion is just a free-text column
in the wear log, and this prompt tells the agent how to reason about it.

RUN (both MCP servers must already be running):
    python agents/trip-planner/agent.py
Try:
    "Pack me for 3 days in San Francisco starting Friday, one nice dinner."
"""

import os
# Force gRPC to use the OS DNS resolver (fixes Vertex "Could not contact DNS
# servers" on macOS/VPN). Must run before the google/grpc imports below.
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Make the project root importable (works from any launch directory, any OS).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_google_vertexai import ChatVertexAI

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — same model/servers as host/, different brain (system prompt)
# ─────────────────────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"
GCP_PROJECT = "wardro-499801"
GCP_LOCATION = "us-central1"

SERVERS = {
    "wardro":   {"url": "http://127.0.0.1:8000/mcp", "transport": "streamable_http"},
    "wardrobe": {"url": "http://127.0.0.1:8001/mcp", "transport": "streamable_http"},
}


def system_prompt() -> str:
    """Built fresh so the agent always knows TODAY's date (it can't guess
    what 'this Friday' means otherwise)."""
    today = datetime.now().strftime("%A, %B %d, %Y")
    return (
        f"You are a trip-packing planner. Today is {today}.\n"
        "\n"
        "Given a destination, trip dates, and any planned activities, produce a "
        "day-by-day packing list using ONLY items the user actually owns.\n"
        "\n"
        "WORKFLOW:\n"
        "1. Resolve relative dates ('this Friday', 'next week') from today's date. "
        "If dates or destination are missing, ask before calling tools.\n"
        "2. geocode the destination, then call get_forecast for EACH trip day "
        "(use hour=12 for daytime and hour=20 if evenings matter). Forecasts only "
        "exist ~7 days out — if the trip is beyond that, say so and plan from "
        "typical conditions instead, clearly labeled as an estimate.\n"
        "3. Call get_wear_counts (since = ~30 days ago) and search_closet to see "
        "what's available. Prefer LESS recently/frequently worn items.\n"
        "4. Build the list: one core outfit per day + weather-driven layers. "
        "Use get_color_matches so pieces mix and match — packing light beats "
        "packing new.\n"
        "\n"
        "RE-WEAR RULES (occasions are free text in the wear log — reason, don't "
        "look for an enum):\n"
        "- An item may repeat at most 2-3 times per trip, and only for DIFFERENT "
        "occasions (e.g. same jeans for travel day and casual dinner: fine; same "
        "shirt for two dinners with the same people: avoid).\n"
        "- Check get_wear_history when unsure what an item was last worn for.\n"
        "\n"
        "OUTPUT: a day-by-day plan (Day 1, Day 2, ...) with the weather one-liner "
        "per day, then a consolidated packing checklist with exact item names "
        "from the closet. Note gaps honestly ('you have no rain layer').\n"
        "\n"
        "AFTER the user confirms the plan, offer to log_wear each item on its "
        "planned date so future packing avoids over-repeating them."
    )


def extract_text(content) -> str:
    """Gemini 2.5 returns content as a LIST of parts; return just the text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        ).strip()
    return str(content)


async def main():
    print("Connecting to MCP servers…")
    client = MultiServerMCPClient(SERVERS)
    tools = await client.get_tools()
    print(f"  ✓ loaded {len(tools)} tools across all servers")

    model = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT, location=GCP_LOCATION)
    agent = create_agent(model, tools, system_prompt=system_prompt())

    print("\nTrip Planner — pack from your own closet. 'quit' to exit.")
    print('Try: "Pack me for 3 days in San Francisco starting Friday, one nice dinner."\n')

    history = []
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        history.append(("user", user_input))
        result = await agent.ainvoke({"messages": history})
        reply = extract_text(result["messages"][-1].content)
        history.append(("assistant", reply))
        print(f"\nPlanner: {reply}\n")

    print("Safe travels!")


if __name__ == "__main__":
    asyncio.run(main())
