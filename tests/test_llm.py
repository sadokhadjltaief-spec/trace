"""LLM gateway tests that need no network: cache, demo mode, token accounting."""
import json

import pytest

from engine import llm


@pytest.fixture
def tmp_llm(tmp_path, monkeypatch):
    base = dict(llm._c())
    base.update(cache_dir=str(tmp_path / "cache"), log_db=str(tmp_path / "trace.db"), min_interval_s=0)
    monkeypatch.setattr(llm, "_c", lambda: base)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    llm.set_demo_mode(False)
    llm.set_session("t")
    yield tmp_path
    llm.set_demo_mode(False)


def _seed_cache(req: llm.Request, text="{}", pt=100, ct=50):
    key = llm._key(req, req.model or llm.default_model())
    (llm._cache_dir() / f"{key}.json").write_text(json.dumps(
        {"text": text, "data": json.loads(text), "prompt_tokens": pt, "completion_tokens": ct}), encoding="utf-8")


def test_cached_replays_are_not_counted_as_tokens(tmp_llm):
    req = llm.Request(messages=[{"role": "user", "content": "hi"}], json_mode=True, purpose="t")
    # one real call (simulated by logging a non-cached response) ...
    llm._log(req, "test-model", llm.Response("{}", {}, "test-model", 100, 50, False, 0.1), 1)
    # ... then three replays from the cache
    _seed_cache(req)
    for _ in range(3):
        r = llm.chat(req)
        assert r.cached
    s = llm.usage_summary("t")["by_model"][0]
    assert s["calls"] == 4 and s["cached_calls"] == 3
    assert s["prompt_tokens"] == 100 and s["completion_tokens"] == 50  # only the real call counts


def test_demo_mode_never_hits_network(tmp_llm):
    llm.set_demo_mode(True)
    with pytest.raises(llm.CacheMiss):
        llm.chat(llm.Request(messages=[{"role": "user", "content": "not cached"}], purpose="t"))


def test_retry_after_parsing():
    class R:  # minimal stand-ins for an HTTP error with headers
        def __init__(self, h):
            self.headers = h

    class E(Exception):
        def __init__(self, h):
            self.response = R(h)

    assert llm._retry_after(E({"retry-after": "3"})) == 3.0
    assert abs(llm._retry_after(E({"x-ratelimit-reset-tokens": "1m2.5s"})) - 62.5) < 1e-9
    assert llm._retry_after(E({})) is None
