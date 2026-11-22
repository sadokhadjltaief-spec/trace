"""Single gateway for every LLM call in TRACE.

- Disk cache in .cache/llm/<sha256(model+request)>.json (demo mode = cache only, no network)
- JSON mode, timeout, retries with exponential backoff; 429 honours retry-after headers
- Per-model throttle (min interval between request starts), shared across threads
- batch() for bulk evals: small thread pool + the same throttle; already-cached items cost nothing
- Token logging to SQLite (.cache/trace.db, table llm_calls)

The LLM never produces probabilities for the diagnosis (see engine/bayes.py).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine import ROOT
from engine.config import cfg, env


class CacheMiss(RuntimeError):
    """Raised in demo/offline mode when a request is not in the cache."""


class LLMError(RuntimeError):
    pass


@dataclass
class Request:
    messages: list[dict]
    model: str | None = None          # default: LLM_MODEL
    json_mode: bool = False
    temperature: float = 0.0
    max_tokens: int | None = None
    purpose: str = ""                 # free-text tag for the log (e.g. "hint", "eval_detector")
    seed_tag: str = ""                # extra cache-key component to get a different sample on purpose
    extra: dict = field(default_factory=dict)


@dataclass
class Response:
    text: str
    data: Any | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    latency_s: float


# ---------------------------------------------------------------- settings / state
_demo_mode = False
_lock = threading.Lock()
_last_start: dict[str, float] = {}
_db_lock = threading.Lock()


def set_demo_mode(on: bool) -> None:
    global _demo_mode
    _demo_mode = bool(on)


def demo_mode() -> bool:
    return _demo_mode or bool(cfg().get("demo_mode"))


def _c() -> dict:
    return cfg()["llm"]


def default_model() -> str:
    m = env("LLM_MODEL")
    if not m:
        raise LLMError("LLM_MODEL is not set (put it in .env)")
    return m


def eval_model() -> str:
    return env("EVAL_MODEL") or default_model()


def _cache_dir() -> Path:
    p = ROOT / _c()["cache_dir"]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _key(req: Request, model: str) -> str:
    payload = {"model": model, "messages": req.messages, "json": req.json_mode,
               "temperature": req.temperature, "max_tokens": req.max_tokens,
               "seed_tag": req.seed_tag, "extra": req.extra,
               "reasoning_effort": _c().get("reasoning_effort")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------- logging
def _db() -> sqlite3.Connection:
    path = ROOT / _c()["log_db"]
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
        ts REAL, session TEXT, purpose TEXT, model TEXT, cached INTEGER,
        prompt_tokens INTEGER, completion_tokens INTEGER, latency_s REAL, attempts INTEGER, error TEXT)""")
    return con


_session_id = "default"


def set_session(session_id: str) -> None:
    global _session_id
    _session_id = session_id


def _log(req: Request, model: str, resp: Response | None, attempts: int, error: str = "") -> None:
    with _db_lock:
        con = _db()
        con.execute("INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?)", (
            time.time(), _session_id, req.purpose, model, int(bool(resp and resp.cached)),
            resp.prompt_tokens if resp else 0, resp.completion_tokens if resp else 0,
            resp.latency_s if resp else 0.0, attempts, error[:300]))
        con.commit()
        con.close()


# ---------------------------------------------------------------- throttle
_tok_window: dict[str, list[tuple[float, int]]] = {}  # model -> [(t, tokens)] in the last 60 s


def estimate_tokens(messages: list[dict], max_tokens: int) -> int:
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return int(chars / 3.5) + max_tokens // 2  # rough: prompt + half the completion budget


def _throttle(model: str, est_tokens: int = 0) -> None:
    """Min interval between request starts + a sliding 60 s token budget (tpm_budget, per model)."""
    gap = float(_c().get("min_interval_s", 0))
    budget = int(_c().get("tpm_budget") or 0)
    while True:
        with _lock:
            now = time.monotonic()
            win = [(t, n) for t, n in _tok_window.get(model, []) if now - t < 60]
            _tok_window[model] = win
            used = sum(n for _, n in win)
            nxt = _last_start.get(model, 0.0) + gap
            over = budget and win and used + est_tokens > budget
            if now >= nxt and not over:
                _last_start[model] = now
                win.append((now, est_tokens))  # reserve; corrected after the response
                return
            wait = max(nxt - now, (win[0][0] + 60 - now) if over else 0, 0.05)
        time.sleep(wait)


def _record_tokens(model: str, est: int, actual: int) -> None:
    with _lock:
        win = _tok_window.get(model, [])
        for i in range(len(win) - 1, -1, -1):
            if win[i][1] == est:
                win[i] = (win[i][0], actual)
                break


def _push_back(model: str, seconds: float) -> None:
    """After a 429, delay every thread using this model."""
    with _lock:
        _last_start[model] = max(_last_start.get(model, 0.0), time.monotonic() + seconds)


def _retry_after(exc: Exception) -> float | None:
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    # per-minute token reset first; the request reset is a DAILY window and only applies when requests ran out
    order = ["retry-after", "x-ratelimit-reset-tokens"]
    if str(headers.get("x-ratelimit-remaining-requests", "1")) == "0":
        order.append("x-ratelimit-reset-requests")
    for h in order:
        v = headers.get(h)
        if not v:
            continue
        try:
            return float(v)
        except ValueError:  # Groq sends durations like "2m59.56s" / "7.66s"
            total, num = 0.0, ""
            for ch in v:
                if ch.isdigit() or ch == ".":
                    num += ch
                elif ch in "hms" and num:
                    total += float(num) * {"h": 3600, "m": 60, "s": 1}[ch]
                    num = ""
            if total:
                return total
    return None


# ---------------------------------------------------------------- core call
_client = None


def _groq():
    global _client
    if _client is None:
        from groq import Groq
        key = env("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY is not set")
        _client = Groq(api_key=key, timeout=float(_c()["timeout_s"]), max_retries=0)
    return _client


def _parse_json(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        s, e = t.find("{"), t.rfind("}")
        if s >= 0 and e > s:
            return json.loads(t[s:e + 1])
        raise


_CAPPED: dict[str, float] = {}  # model -> time its daily cap was hit (skip it for a while, go to the fallback)


def _fallbacks(model: str) -> list[str]:
    """config llm.fallback_models: tried in order when `model` hits Groq's DAILY cap (team decision 2026-11-22)."""
    return [m for m in (_c().get("fallback_models") or []) if m != model]


def _from_cache(req: Request, model: str) -> Response | None:
    cpath = _cache_dir() / f"{_key(req, model)}.json"
    if not cpath.exists():
        return None
    d = json.loads(cpath.read_text(encoding="utf-8"))
    resp = Response(d["text"], d.get("data"), model, d.get("prompt_tokens", 0), d.get("completion_tokens", 0), True, 0.0)
    _log(req, model, resp, 0)
    return resp


def chat(req: Request, _fallback: bool = True) -> Response:
    model = req.model or default_model()
    hit = _from_cache(req, model)
    if hit:
        return hit
    if _fallback:  # an answer recorded earlier by a fallback model (quota day) replays offline too
        for fb in _fallbacks(model):
            hit = _from_cache(req, fb)
            if hit:
                return hit
    if demo_mode():
        _log(req, model, None, 0, "cache miss in demo mode")
        raise CacheMiss(f"not cached (demo mode): purpose={req.purpose}")
    if _fallback and time.time() - _CAPPED.get(model, 0) < 3600:
        return _chat_fallback(req, model, "daily cap hit earlier")
    try:
        return _chat_live(req, model)
    except LLMError as e:
        if _fallback and "daily cap" in str(e):
            _CAPPED[model] = time.time()
            return _chat_fallback(req, model, str(e))
        if _fallback and re.search(r"HTTP 400|bad JSON|HTTP 5\d\d", str(e)):
            return _chat_fallback(req, model, str(e))  # malformed output or server error: the next model may do it
        raise


def _chat_fallback(req: Request, model: str, why: str) -> Response:
    last = why
    for fb in _fallbacks(model):
        if time.time() - _CAPPED.get(fb, 0) < 3600:
            continue
        try:
            return _chat_live(Request(**{**req.__dict__, "model": fb}), fb)
        except LLMError as e:
            last = str(e)
            if "daily cap" in last:
                _CAPPED[fb] = time.time()
    raise LLMError(f"all models unavailable: {last[:200]}")


def _chat_live(req: Request, model: str) -> Response:
    key = _key(req, model)
    cpath = _cache_dir() / f"{key}.json"

    from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

    c = _c()
    attempts, last_err = 0, ""
    while attempts < int(c["retries"]):
        attempts += 1
        est = estimate_tokens(req.messages, req.max_tokens or int(c["max_tokens"]))
        _throttle(model, est)
        t0 = time.monotonic()
        try:
            kwargs: dict[str, Any] = dict(model=model, messages=req.messages,
                                          temperature=req.temperature,
                                          max_tokens=req.max_tokens or int(c["max_tokens"]))
            if req.json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if "gpt-oss" in model and c.get("reasoning_effort"):
                kwargs["reasoning_effort"] = c["reasoning_effort"]
            kwargs.update(req.extra)
            out = _groq().chat.completions.create(**kwargs)
            text = out.choices[0].message.content or ""
            data = _parse_json(text) if req.json_mode else None
            u = out.usage
            resp = Response(text, data, model, getattr(u, "prompt_tokens", 0) or 0,
                            getattr(u, "completion_tokens", 0) or 0, False, time.monotonic() - t0)
            _record_tokens(model, est, resp.prompt_tokens + resp.completion_tokens)
            cpath.write_text(json.dumps({"text": text, "data": data, "prompt_tokens": resp.prompt_tokens,
                                         "completion_tokens": resp.completion_tokens,
                                         "model": model, "purpose": req.purpose}, ensure_ascii=False),
                             encoding="utf-8")
            _log(req, model, resp, attempts)
            return resp
        except RateLimitError as e:
            if "per day" in str(e):  # daily cap (TPD/RPD): retrying for minutes cannot help; caller falls back
                last_err = f"429 daily cap: {str(e)[:160]}"
                break
            wait = _retry_after(e) or min(c["backoff_max_s"], c["backoff_base_s"] * 2 ** attempts)
            wait += random.uniform(0, 1)
            last_err = f"429: waited {wait:.1f}s"
            _push_back(model, wait)
        except (APITimeoutError, APIConnectionError) as e:
            last_err = f"{type(e).__name__}"
            time.sleep(min(c["backoff_max_s"], c["backoff_base_s"] * 2 ** attempts))
        except APIStatusError as e:
            last_err = f"HTTP {e.status_code}: {str(e)[:200]}"
            if e.status_code == 400 and re.search(r"Failed to generate JSON|called a tool|json_validate", str(e)):
                # the model's output was malformed this time (Groq JSON mode): a new sample usually works
                req = Request(**{**req.__dict__, "seed_tag": req.seed_tag + "|resample"})
                if attempts >= 3:
                    break
                continue
            if e.status_code < 500 and e.status_code != 408:
                break  # 4xx (not 429/408) will not succeed on retry
            time.sleep(min(c["backoff_max_s"], c["backoff_base_s"] * 2 ** attempts))
        except (json.JSONDecodeError, ValueError) as e:
            last_err = f"bad JSON: {e}"
            req = Request(**{**req.__dict__, "seed_tag": req.seed_tag + "|retry"})
    _log(req, model, None, attempts, last_err)
    raise LLMError(f"LLM call failed after {attempts} attempts: {last_err}")


def ask_json(system: str, user: str, *, purpose: str, model: str | None = None,
             temperature: float = 0.0, **kw) -> dict:
    r = chat(Request(messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                     model=model, json_mode=True, temperature=temperature, purpose=purpose, **kw))
    return r.data


def batch(reqs: list[Request], workers: int | None = None, on_error: str = "keep") -> list[Response | Exception]:
    """Run many requests with the shared throttle. Cached ones return instantly.
    on_error='keep' returns the exception in place of the response; 'raise' re-raises."""
    workers = workers or int(_c().get("batch_workers", 2))

    def one(r: Request):
        try:
            return chat(r)
        except Exception as e:  # noqa: BLE001
            if on_error == "raise":
                raise
            return e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, reqs))


def usage_summary(session: str | None = None) -> dict:
    con = _db()
    # tokens are counted only for real (non-cached) calls; cached replays cost nothing
    q = ("SELECT model, SUM(cached), COUNT(*), SUM(CASE WHEN cached=0 THEN prompt_tokens ELSE 0 END), "
         "SUM(CASE WHEN cached=0 THEN completion_tokens ELSE 0 END) FROM llm_calls")
    args: tuple = ()
    if session:
        q += " WHERE session=?"
        args = (session,)
    rows = con.execute(q + " GROUP BY model", args).fetchall()
    con.close()
    c = _c()
    return {"cost_label": c.get("cost_label"),
            "by_model": [{"model": m, "calls": n, "cached_calls": cc, "prompt_tokens": pt or 0,
                          "completion_tokens": ct or 0} for m, cc, n, pt, ct in rows],
            "price_input_per_m": c.get("price_input_per_m"),
            "price_output_per_m": c.get("price_output_per_m")}
