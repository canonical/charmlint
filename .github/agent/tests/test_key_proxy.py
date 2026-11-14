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


def test_cost_in_without_usage() -> None:
    assert key_proxy.Handler.cost_in(b'{"choices": []}') == 0.0


def test_cost_of_tokens_without_a_cost() -> None:
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    assert key_proxy.cost_of(usage) == pytest.approx(1500 * key_proxy.FALLBACK_USD_PER_TOKEN)
