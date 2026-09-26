"""
host/mcp_client.py — a hand-rolled MCP CLIENT for Streamable HTTP. Pure stdlib.

This is the client-side twin of shared/mcp_server.py. Together they show BOTH ends
of the protocol with zero libraries: mcp_server.py answers JSON-RPC over HTTP;
this file asks the questions. It replaces `langchain_mcp_adapters.
MultiServerMCPClient` (which replaced the MCPHub class in _archive/gemini_host.py,
which used the `mcp` SDK — this version needs none of them).

THE PROTOCOL, in full (JSON-RPC 2.0 over HTTP POST):

    client                                server
    ──────                                ──────
    POST {method:"initialize", id:1}  ──▶
                                      ◀── 200 {result:{capabilities,...}}
                                          + header Mcp-Session-Id: abc123
    POST {method:"notifications/initialized"}   (a NOTIFICATION: no "id")
                                      ◀── 202, empty body (notifications get no reply)
    POST {method:"tools/list", id:2}  ──▶
                                      ◀── 200 {result:{tools:[...]}}
    POST {method:"tools/call", id:3,
          params:{name, arguments}}   ──▶
                                      ◀── 200 {result:{content:[{type:"text",text}]}}

TEST IT STANDALONE (both servers must be running):
    python host/mcp_client.py
"""

import json
import urllib.request

# below is MCP client; one instance will maintain one connection to one server.
class MCPConnection:
    """One client connection to ONE MCP server over Streamable HTTP."""

    def __init__(self, name: str, url: str):
        self.name = name          # our nickname for the server ("wardro")
        self.url = url            # e.g. http://127.0.0.1:8000/mcp
        self.session_id = None    # handed to us by the server on initialize
        self._next_id = 0         # JSON-RPC ids just need to be unique per request

    # ── the one transport primitive: POST a JSON body, read a JSON body ──
    def _post(self, message: dict) -> dict | None:
        """Send one JSON-RPC message; return the parsed reply (None for 202s)."""
        data = json.dumps(message).encode()
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        # The MCP spec says clients MUST accept both plain JSON and SSE replies.
        # Our MiniMCP only ever sends JSON, but sending this header means this
        # client also satisfies stricter servers (e.g. FastMCP).
        req.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            req.add_header("Mcp-Session-Id", self.session_id)

        with urllib.request.urlopen(req, timeout=30) as resp:
            # initialize hands us a session id in a response HEADER — remember it
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            body = resp.read()
            if not body:                      # 202 for notifications: empty body
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                # SSE framing: lines like "data: {...}". MiniMCP never sends
                # this, but FastMCP does — parse it so the client works there too.
                for line in body.decode().splitlines():
                    if line.startswith("data:"):
                        return json.loads(line[len("data:"):].strip())
                return None
            return json.loads(body)

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        """Send a REQUEST (has an id → expects a result) and unwrap the reply."""
        self._next_id += 1
        reply = self._post({
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        })
        if reply is None:
            raise RuntimeError(f"{self.name}: no reply to {method}")
        if "error" in reply:
            raise RuntimeError(f"{self.name}: {method} -> {reply['error'].get('message')}")
        return reply["result"]

    def _notify(self, method: str):
        """Send a NOTIFICATION (no id → no reply expected)."""
        self._post({"jsonrpc": "2.0", "method": method})

    # ── the MCP handshake + the two calls a host actually uses ──
    def connect(self) -> list[dict]:
        """initialize → notifications/initialized → tools/list."""
        self._rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "wardro-host", "version": "0.1.0"},
        })
        self._notify("notifications/initialized")   # "handshake done, ready"
        return self._rpc("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict):
        """tools/call → unwrap MCP content blocks → parse JSON if possible.

        MCP tool results arrive as a LIST of content blocks (text, images, ...).
        Our tools only ever return one text block containing JSON, so: join the
        text blocks, then try json.loads — same unwrapping the adapter did.
        """
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        text = "\n".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"result": text}


class MCPHub:
    """Connections to EVERY server + one flat tool list. Replaces
    MultiServerMCPClient: connect to each server, merge the tool lists,
    remember which server owns which tool, route calls accordingly."""

    def __init__(self, servers: dict[str, str]):
        """servers: {"wardro": "http://127.0.0.1:8000/mcp", ...}"""
        self._connections = {n: MCPConnection(n, url) for n, url in servers.items()}
        self.tools: list[dict] = []          # merged [{name, description, inputSchema, server}]
        self._owner: dict[str, MCPConnection] = {}   # tool name -> connection

    def connect_all(self):
        for name, conn in self._connections.items():
            for tool in conn.connect():
                tool["server"] = name
                self.tools.append(tool)
                self._owner[tool["name"]] = conn
            print(f"  ✓ {name}: {sum(1 for t in self.tools if t['server'] == name)} tools")

    def call_tool(self, name: str, arguments: dict):
        conn = self._owner.get(name)
        if conn is None:
            return {"error": f"No server owns tool '{name}'"}
        try:
            return conn.call_tool(name, arguments)
        except Exception as e:                      # network error, server died, ...
            return {"error": f"{type(e).__name__}: {e}"}


# ── standalone self-test: run me directly to prove the client works ──
if __name__ == "__main__":
    hub = MCPHub({
        "wardro":   "http://127.0.0.1:8000/mcp",
        "wardrobe": "http://127.0.0.1:8001/mcp",
    })
    print("Connecting…")
    hub.connect_all()
    print(f"\nAll {len(hub.tools)} tools the host sees:")
    for t in hub.tools:
        print(f"  [{t['server']}] {t['name']}")

    print("\nCalling outfit_advice(temp_f=55) …")           # pure logic, no internet
    print(" ", hub.call_tool("outfit_advice", {"temp_f": 55}))
    print("\nCalling get_color_matches(color='navy') …")     # closet DB read
    print(" ", hub.call_tool("get_color_matches", {"color": "navy"}))
    print("\nCalling a tool that doesn't exist …")
    print(" ", hub.call_tool("nope", {}))
