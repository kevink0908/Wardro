"""
shared/mcp_server.py — a tiny MCP server, built FROM SCRATCH. No `mcp` library, no
FastMCP. It shows what FastMCP does under the hood for BOTH transports:

  • run()       -> stdio            (host launches this script, talks over pipes)
  • run_http()  -> Streamable HTTP  (this script listens on a URL; host connects)

KEY IDEA: the PROTOCOL is the same for both — JSON-RPC 2.0 messages (initialize,
tools/list, tools/call). Only the PIPE the bytes travel through changes (stdin/
stdout vs an HTTP request/response). That's why `_handle` / `_reply_for` below
are shared, and only `run` vs `run_http` differ.

GOLDEN RULE (stdio): stdout is the protocol channel — NEVER print() to it; logs -> stderr.
"""

import sys
import json
import uuid
import inspect
import http.server                           # Python's built-in replacement for FastMCP
# NOTE: http.server replaces FastMCP's job when handling HTTP responses.

def _log(*a):
    print(*a, file=sys.stderr, flush=True)   # humans read stderr; stdout is the protocol


def _schema_for(func):
    """Build a minimal JSON Schema from a function's params (what FastMCP does
    automatically from your type hints)."""
    py_to_json = {int: "integer", float: "number", bool: "boolean", str: "string"}
    props, required = {}, []
    for name, p in inspect.signature(func).parameters.items():
        props[name] = {"type": py_to_json.get(p.annotation, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


class MiniMCP:
    def __init__(self, name):
        self.name = name
        self._tools = {}

    def tool(self):
        """register mcp tools."""
        def register(func):
            self._tools[func.__name__] = {
                "func": func,
                "description": (func.__doc__ or "").strip(),
                "schema": _schema_for(func),
            }
            return func
        return register

    # ── MCP protocol logic (transport-INDEPENDENT) ──
    def _handle(self, method, params):
        # make wardro server visible.
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": "0.1.0"},
            }
        # provide a list of tools that the MCP server has and each tool's info.
        if method == "tools/list":
            return {"tools": [
                {"name": n, "description": t["description"], "inputSchema": t["schema"]}
                for n, t in self._tools.items()
            ]}
        # run a specific tool with given inputs,
        if method == "tools/call":
            result = self._tools[params["name"]]["func"](**(params.get("arguments") or {}))
            text = result if isinstance(result, str) else json.dumps(result)
            return {"content": [{"type": "text", "text": text}]}
        if method == "ping":
            return {}
        raise ValueError(f"Unknown method: {method}")

    def _reply_for(self, msg):
        """One incoming JSON-RPC message -> a reply dict (or None for a
        notification, which gets no reply). Shared by both transports."""
        msg_id = msg.get("id")
        if msg_id is None:                       # notification -> no reply
            return None
        try:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "result": self._handle(msg.get("method"), msg.get("params") or {})}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32000, "message": str(e)}}

    # ── TRANSPORT 1: stdio ──
    def run(self):
        _log(f"[my_mcp] '{self.name}' stdio · {len(self._tools)} tools · waiting on stdin…")
        while True:
            line = sys.stdin.readline()
            if line == "":
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = self._reply_for(msg)
            if reply is not None:
                sys.stdout.write(json.dumps(reply) + "\n")
                sys.stdout.flush()

    # ── TRANSPORT 2: Streamable HTTP (a minimal, from-scratch web server) ──
    # NOTE: this is the HTTP server handles the full request->response cycle.
    def run_http(self, host="127.0.0.1", port=8000, path="/mcp"):
        server = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass  # silence the default access log
            # NOTE: _write() sends JSON responses
            def _write(self, code, body=None, extra=None):
                self.send_response(code)
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                if body is None:
                    self.end_headers()
                    return
                data = json.dumps(body).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            # NOTE: do_POST() receives HTTP request and parses JSON
            def do_POST(self):
                if self.path.rstrip("/") != path.rstrip("/"):   # (a) check the URL is /mcp
                    self._write(404); return
                n = int(self.headers.get("Content-Length", 0))  # (b) how many bytes is the body?
                try:
                    msg = json.loads(self.rfile.read(n))    # (c) ← READ + PARSE the JSON here
                except Exception:
                    self._write(400); return
                reply = server._reply_for(msg)              # (d) hand it to the brain
                if reply is None: 
                    # notification -> 202, no body                       
                    self._write(202); return
                extra = {}
                if msg.get("method") == "initialize":    # hand the client a session id
                    extra["Mcp-Session-Id"] = uuid.uuid4().hex
                # (e) send the answer (via _write)
                self._write(200, reply, extra)
            def do_GET(self):
                self._write(405)   # we don't offer the optional server->client SSE stream
        httpd = http.server.ThreadingHTTPServer((host, port), Handler)
        _log(f"[my_mcp] '{self.name}' HTTP on http://{host}:{port}{path} · {len(self._tools)} tools")
        httpd.serve_forever()
