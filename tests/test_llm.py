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
    # the daily request reset must NOT be used for a per-minute token 429
    assert llm._retry_after(E({"x-ratelimit-reset-requests": "47m31s", "x-ratelimit-reset-tokens": "0.7s",
                               "x-ratelimit-remaining-requests": "900"})) == 0.7
    assert llm._retry_after(E({"x-ratelimit-reset-requests": "2m", "x-ratelimit-remaining-requests": "0"})) == 120


def test_token_budget_throttle_waits(monkeypatch):
    base = dict(llm._c())
    base.update(min_interval_s=0, tpm_budget=1000)
    monkeypatch.setattr(llm, "_c", lambda: base)
    llm._tok_window["m"] = [(llm.time.monotonic() - 59.8, 900)]  # 900 tokens used, expires in 0.2 s
    t0 = llm.time.monotonic()
    llm._throttle("m", 300)
    assert llm.time.monotonic() - t0 >= 0.15
    llm._tok_window.pop("m", None)


def test_daily_cap_fails_fast(monkeypatch, tmp_path):
    import httpx
    from groq import RateLimitError
    calls = []

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    calls.append(1)
                    r = httpx.Response(429, request=httpx.Request("POST", "https://x"), headers={"retry-after": "31"})
                    raise RateLimitError("Rate limit reached ... on tokens per day (TPD): Limit 200000",
                                         response=r, body=None)
    monkeypatch.setattr(llm, "_groq", lambda: Fake)
    monkeypatch.setattr(llm, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(llm, "_throttle", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_log", lambda *a, **k: None)  # never write test rows into the real call log
    monkeypatch.setattr(llm, "_CAPPED", {})
    with pytest.raises(llm.LLMError, match="daily cap"):
        llm.chat(llm.Request(messages=[{"role": "user", "content": "x"}], purpose="test_tpd"))
    assert len(calls) == len(llm._c()["fallback_models"])  # one try per model, no retries


def test_daily_cap_moves_to_the_next_model_and_replays_offline(monkeypatch, tmp_path):
    import httpx
    from types import SimpleNamespace
    from groq import RateLimitError
    used = []

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    used.append(kw["model"])
                    if kw["model"] == "openai/gpt-oss-120b":
                        r = httpx.Response(429, request=httpx.Request("POST", "https://x"))
                        raise RateLimitError("Rate limit reached ... tokens per day (TPD)", response=r, body=None)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": 1}'))],
                                           usage=SimpleNamespace(prompt_tokens=3, completion_tokens=2))
    monkeypatch.setattr(llm, "_groq", lambda: Fake)
    monkeypatch.setattr(llm, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(llm, "_throttle", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_log", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_CAPPED", {})
    req = dict(messages=[{"role": "user", "content": "x"}], purpose="t", json_mode=True, model="openai/gpt-oss-120b")
    r = llm.chat(llm.Request(**req))
    assert r.data == {"ok": 1} and r.model == "openai/gpt-oss-20b"
    assert used == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    monkeypatch.setattr(llm, "_demo_mode", True)                     # offline: the fallback answer replays
    assert llm.chat(llm.Request(**req)).data == {"ok": 1} and len(used) == 2
