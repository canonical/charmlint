"""The key proxy's path check and cost accounting."""

from __future__ import annotations

import json

import key_proxy
import pytest


def handler(path: str) -> key_proxy.Handler:
    h = object.__new__(key_proxy.Handler)
    h.path = path
    return h


@pytest.mark.parametrize(
    ("path", "clean"),
    [
        ("/api/v1/models", "/api/v1/models"),
        ("/api/v1/generation?id=abc", "/api/v1/generation"),
        ("http://evil.example/api/v1/models", None),
        ("//evil.example/api/v1/models", None),
        ("/api/v1/../../x", None),
        ("/api/v1/%2e%2e/x", None),
        ("/api//v1/models", None),
        ("/api\\v1", None),
    ],
)
def test_clean_path(path: str, clean: str | None) -> None:
    assert handler(path).clean_path() == clean


def test_target_re_encodes_the_query() -> None:
    assert handler("/api/v1/generation?id=a b&x=1").target() == "/api/v1/generation?id=a+b&x=1"


def test_cost_in_json() -> None:
    body = json.dumps({"usage": {"cost": 0.25}}).encode()
    assert key_proxy.Handler.cost_in(body) == 0.25


def test_cost_in_stream() -> None:
    body = (
        b'data: {"choices": []}\n\n'
        b'data: {"choices": [], "usage": {"cost": 0.5}}\n\n'
        b"data: [DONE]\n\n"
    )
    assert key_proxy.Handler.cost_in(body) == 0.5


def test_cost_in_json_that_mentions_a_stream() -> None:
    body = b'{"choices": [{"message": {"content": "send data: now"}}], "usage": {"cost": 0.25}}'
    assert key_proxy.Handler.cost_in(body) == 0.25


def test_cost_in_without_usage() -> None:
    assert key_proxy.Handler.cost_in(b'{"choices": []}') == 0.0


def test_cost_of_tokens_without_a_cost() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    assert key_proxy.cost_of(usage) == pytest.approx(1500 * key_proxy.FALLBACK_USD_PER_TOKEN)


@pytest.fixture
def models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(key_proxy.State, "models", frozenset({"z-ai/glm-5.3"}))


def request(**extra: object) -> dict:
    return {"model": "z-ai/glm-5.3", "messages": [{"role": "user", "content": "hi"}], **extra}


@pytest.mark.usefixtures("models")
def test_prepare_pins_the_provider_and_caps_the_output() -> None:
    data, reserve = key_proxy.prepare(request(provider={"only": ["cheap"]}, max_tokens=True))
    sent = json.loads(data)
    assert sent["provider"] == key_proxy.ROUTING["z-ai/"]
    assert sent["max_tokens"] == key_proxy.MAX_OUTPUT_TOKENS
    assert reserve > key_proxy.MAX_OUTPUT_TOKENS * key_proxy.RESERVE_USD_PER_OUTPUT_TOKEN


@pytest.mark.usefixtures("models")
@pytest.mark.parametrize(
    "body",
    [
        {"model": "openai/gpt-5", "messages": []},
        request(tools=[{"type": "openrouter:web_search"}]),
        request(tools=[{"type": "openrouter:subagent", "parameters": {"model": "x/y"}}]),
        request(messages=[{"role": "user", "content": [{"type": "file", "file": {}}]}]),
        request(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "https://evil.example"}}
                    ],
                }
            ]
        ),
    ],
)
def test_prepare_refuses(body: dict) -> None:
    with pytest.raises(PermissionError):
        key_proxy.prepare(body)


@pytest.mark.usefixtures("models")
def test_prepare_allows_function_tools_and_inline_images() -> None:
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
    body = request(
        tools=[{"type": "function", "function": {"name": "read"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "x"}, image]}],
    )
    key_proxy.prepare(body)


def test_the_pipeline_can_ask_what_has_been_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    import http.server
    import threading
    import urllib.request

    monkeypatch.setattr(key_proxy.State, "spent", 1.5)
    monkeypatch.setattr(key_proxy.State, "reserved", 0.25)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), key_proxy.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/proxy/spent"
        with urllib.request.urlopen(url, timeout=5) as r:
            assert json.loads(r.read()) == {"spent": 1.5, "reserved": 0.25}
    finally:
        server.shutdown()


def test_headers_the_proxy_sets_go_upstream_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import http.client
    import http.server
    import threading

    sent: list[dict[str, str]] = []

    class Upstream:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def connect(self) -> None:
            pass

        def request(self, *_: object, headers: dict[str, str], **__: object) -> None:
            sent.append(headers)
            raise http.client.HTTPException("stop here")

        def close(self) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), key_proxy.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    monkeypatch.setattr(http.client, "HTTPSConnection", Upstream)
    monkeypatch.setattr(key_proxy.State, "budget", 10.0)
    monkeypatch.setattr(key_proxy.State, "models", frozenset({"a/b"}))
    monkeypatch.setattr(key_proxy.State, "spent", 0.0)
    monkeypatch.setattr(key_proxy.State, "reserved", 0.0)
    try:
        client.request(
            "POST",
            "/api/v1/chat/completions",
            body=json.dumps({"model": "a/b", "messages": []}),
            headers={"content-type": "application/json", "accept-encoding": "gzip"},
        )
        assert client.getresponse().status == 502
    finally:
        client.close()
        server.shutdown()
    [headers] = sent
    names = [k.lower() for k in headers]
    assert names.count("content-type") == 1
    assert names.count("accept-encoding") == 1
    assert headers["Accept-Encoding"] == "identity"


def test_a_request_once_the_budget_is_spent_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    import http.client
    import http.server
    import threading

    def upstream(*_: object, **__: object) -> None:
        raise AssertionError("nothing should be sent upstream")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), key_proxy.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    monkeypatch.setattr(http.client, "HTTPSConnection", upstream)
    monkeypatch.setattr(key_proxy.State, "budget", 10.0)
    monkeypatch.setattr(key_proxy.State, "models", frozenset({"a/b"}))
    monkeypatch.setattr(key_proxy.State, "spent", 9.5)
    monkeypatch.setattr(key_proxy.State, "reserved", 0.5)
    try:
        client.request(
            "POST",
            "/api/v1/chat/completions",
            body=json.dumps({"model": "a/b", "messages": []}),
            headers={"Content-Type": "application/json"},
        )
        assert client.getresponse().status == 402
    finally:
        client.close()
        server.shutdown()
    assert key_proxy.State.reserved == 0.5
