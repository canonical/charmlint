"""Hold the OpenRouter key outside the agent's reach, and hold the agent to its budget.

The proxy runs as its own user and reads the key from standard input, so it is
in neither its environment nor its command line. The agent's tools run as
another user, and pi is pointed here with a placeholder key. Everything the
runner enforces lives here, because the agent can rewrite or stop anything
running as its own user:

- only the listed models, each pinned to its first-party provider;
- no fallback models, plugins (such as web search) or routing overrides;
- a spending cap, from the cost OpenRouter reports for each response. Each
  request reserves a worst-case cost before it is sent, and a response that
  doesn't finish is charged that reservation, so cutting streams short or
  sending many requests at once doesn't get past the cap;
- a few requests at a time;
- only paths on openrouter.ai, with the Host header the proxy sets.

    echo "$KEY" | python3 key_proxy.py --port 8787 --budget 9 --models a/b,c/d &
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import json
import ssl
import sys
import threading
import urllib.parse

UPSTREAM = "openrouter.ai"
POST_PATHS = {"/api/v1/chat/completions"}
GET_PATHS = {"/api/v1/models", "/api/v1/generation"}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "authorization",
    "content-length",
    "accept-encoding",
}
ROUTING = {
    "z-ai/": {"only": ["z-ai"], "allow_fallbacks": False},
    "moonshotai/": {"only": ["moonshotai"], "allow_fallbacks": False},
}
# When a response carries token counts but no cost, assume a price above any
# allowed model's, so the cap errs towards stopping early.
FALLBACK_USD_PER_TOKEN = 10 / 1_000_000
# The reservation for a request: its body length as an upper bound on input
# tokens, and the output cap, both at prices above any allowed model's.
RESERVE_USD_PER_INPUT_BYTE = 2 / 1_000_000
RESERVE_USD_PER_OUTPUT_TOKEN = 10 / 1_000_000
MAX_OUTPUT_TOKENS = 32768


class State:
    key = ""
    budget = 0.0
    models: frozenset[str] = frozenset()
    spent = 0.0
    reserved = 0.0
    lock = threading.Lock()
    slots = threading.BoundedSemaphore(4)


def cost_of(usage: dict) -> float:
    if isinstance(usage.get("cost"), (int, float)):
        return float(usage["cost"])
    tokens = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
    return tokens * FALLBACK_USD_PER_TOKEN


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.clean_path() not in GET_PATHS:
            self.send_error(403, "not forwarded")
            return
        self.forward(None)

    def do_POST(self) -> None:
        if self.clean_path() not in POST_PATHS:
            self.send_error(403, "not forwarded")
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            self.send_error(400, "not JSON")
            return
        model = body.get("model") if isinstance(body, dict) else None
        if model not in State.models:
            self.send_error(403, "model not allowed")
            return
        for field in ("models", "plugins", "route", "provider", "usage"):
            body.pop(field, None)
        routing = next((r for prefix, r in ROUTING.items() if model.startswith(prefix)), None)
        if routing:
            body["provider"] = routing
        # Always report the cost, so the cap can count it.
        body["usage"] = {"include": True}
        requested = body.pop("max_completion_tokens", None) or body.get("max_tokens")
        if not isinstance(requested, int) or not 0 < requested <= MAX_OUTPUT_TOKENS:
            requested = MAX_OUTPUT_TOKENS
        body["max_tokens"] = requested
        data = json.dumps(body).encode()
        reserve = len(data) * RESERVE_USD_PER_INPUT_BYTE + requested * RESERVE_USD_PER_OUTPUT_TOKEN
        self.forward(data, reserve)

    def clean_path(self) -> str | None:
        """The path and query to send upstream, or None if it tries to escape.

        Only an origin-form target (``/path?query``) is accepted: an absolute
        URL would name another host for the request that carries the key.
        """
        if not self.path.startswith("/") or self.path.startswith("//"):
            return None
        parts = urllib.parse.urlsplit(self.path)
        if parts.scheme or parts.netloc:
            return None
        path = parts.path
        if ".." in path or "%" in path or "//" in path or "\\" in path:
            return None
        return path

    def target(self) -> str:
        """The upstream request target: the checked path, and the query re-encoded."""
        path = self.clean_path()
        if path is None:
            raise ValueError("the path was not checked")
        query = urllib.parse.urlencode(
            urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)
        )
        return f"{path}?{query}" if query else path

    def forward(self, body: bytes | None, reserve: float = 0.0) -> None:
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
        headers["Host"] = UPSTREAM
        headers["Authorization"] = f"Bearer {State.key}"
        headers["Accept-Encoding"] = "identity"
        if body is not None:
            headers["Content-Type"] = "application/json"
        with State.slots:
            # Check and reserve once this request holds a slot, so requests
            # queued while nothing was spent can't all get through.
            with State.lock:
                if State.spent + State.reserved >= State.budget:
                    self.send_error(402, f"budget of ${State.budget:.2f} spent")
                    return
                State.reserved += reserve
            cost: float | None = None
            conn = http.client.HTTPSConnection(
                UPSTREAM, timeout=900, context=ssl.create_default_context()
            )
            try:
                conn.request(self.command, self.target(), body=body, headers=headers)
                resp = conn.getresponse()
                self.send_response(resp.status, resp.reason)
                for k, v in resp.getheaders():
                    if k.lower() not in HOP_BY_HOP:
                        self.send_header(k, v)
                # Re-chunk, so streamed (SSE) responses reach pi as they arrive.
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                seen = bytearray()
                while chunk := resp.read1(65536):
                    seen += chunk
                    self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                cost = self.cost_in(bytes(seen))
                if not cost and resp.status < 400 and body is not None:
                    # A completed request that reported no usage may still
                    # have been billed.
                    cost = reserve
            except (OSError, http.client.HTTPException) as e:
                self.log_error("upstream error: %s", e)
                self.close_connection = True
            finally:
                conn.close()
                # A response that didn't finish may still have been billed:
                # charge what was reserved for it.
                self.charge(reserve if cost is None else cost, reserve)

    @staticmethod
    def cost_in(data: bytes) -> float:
        """The cost of a response: plain JSON, or the usage in an SSE stream."""
        cost = 0.0
        texts = [data]
        if b"data:" in data:
            texts = [line[5:] for line in data.splitlines() if line.startswith(b"data:")]
        for text in texts:
            try:
                usage = json.loads(text).get("usage")
            except (ValueError, AttributeError):
                continue
            if isinstance(usage, dict):
                cost += cost_of(usage)
        return cost

    def charge(self, cost: float, reserve: float) -> None:
        with State.lock:
            State.reserved -= reserve
            State.spent += cost
            spent = State.spent
        if cost:
            self.log_message("cost $%.4f, spent $%.4f of $%.2f", cost, spent, State.budget)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--budget", type=float, required=True)
    parser.add_argument("--models", required=True, help="comma-separated OpenRouter slugs")
    args = parser.parse_args()
    State.key = sys.stdin.readline().strip()
    if not State.key:
        raise SystemExit("no key on standard input")
    State.budget = args.budget
    State.models = frozenset(m.strip() for m in args.models.split(",") if m.strip())
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
