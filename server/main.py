"""HTTP layer over engine/api.py for the Next.js frontend (docs/TEAMMATE_INSTRUCTIONS.md).

One endpoint per engine.api function; responses are the contract models (engine/contract.py), so the OpenAPI
schema at /openapi.json documents every shape. No logic here: no diagnosis math, no LLM calls, no text.

Run:  .\\.venv\\Scripts\\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
Single worker only: sessions live in memory and the engine has per-process state (LLM session tag, demo mode),
so every request is serialised by one lock.
"""
from __future__ import annotations

import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine import api
from engine.config import cfg
from engine.contract import (CONTRACT_VERSION, MisconceptionView, NextQuestion, SessionState, SessionSummary,
                             StudioOutput, TutorTurn)

app = FastAPI(title="TRACE engine API", version=CONTRACT_VERSION,
              description="Thin HTTP wrapper over engine/api.py. Shapes: docs/INTERFACE.md.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])
_lock = threading.Lock()


class Student(BaseModel):
    name: str = ""
    level: str = ""
    lang: Literal["fr", "ar", "en"] = "fr"


class StartBody(BaseModel):
    student: Student
    profile: dict = Field(default_factory=dict)
    demo: bool = False


class AnswerBody(BaseModel):
    question_id: str
    option: str
    confidence: Literal["sure", "unsure"]
    explanation: str | None = None


class ReplyBody(BaseModel):
    choice: str | None = None   # HINT_k / TRANSFER: option letter. RECONSTRUCT: number of the wrong step.
    text: str | None = None     # RECONSTRUCT: why that step is wrong


class StudioBody(BaseModel):
    tool: str
    source: dict = Field(default_factory=dict)


def _call(fn, *a, **kw):
    """Map engine errors to HTTP codes; serialise access to the engine."""
    with _lock:
        try:
            return fn(*a, **kw)
        except KeyError as e:
            raise HTTPException(404, f"unknown session or id: {e}") from None
        except NotImplementedError as e:
            raise HTTPException(501, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from None


@app.get("/api/v1/health")
def health() -> dict:
    return {"ok": True, "contract_version": CONTRACT_VERSION,
            "allow_unverified_dev": bool(cfg().get("live", {}).get("allow_unverified_dev", False))}


@app.post("/api/v1/sessions", response_model=SessionState)
def start_session(body: StartBody):
    return _call(api.start_session, body.student.model_dump(), body.profile, demo=body.demo)


@app.get("/api/v1/sessions/{sid}", response_model=SessionState)
def get_state(sid: str):
    return _call(api.get_state, sid)


@app.get("/api/v1/sessions/{sid}/next", response_model=NextQuestion)
def next_question(sid: str):
    return _call(api.next_question, sid)


@app.post("/api/v1/sessions/{sid}/answer", response_model=TutorTurn)
def submit_answer(sid: str, body: AnswerBody):
    return _call(api.submit_answer, sid, body.question_id, body.option, body.confidence, body.explanation)


@app.post("/api/v1/sessions/{sid}/reply", response_model=TutorTurn)
def tutor_reply(sid: str, body: ReplyBody):
    return _call(api.tutor_reply, sid, text=body.text, choice=body.choice)


@app.get("/api/v1/sessions/{sid}/summary", response_model=SessionSummary)
def summary(sid: str):
    return _call(api.summary, sid)


@app.post("/api/v1/sessions/{sid}/studio", response_model=StudioOutput)
def studio(sid: str, body: StudioBody):
    return _call(api.studio_generate, sid, body.tool, body.source)


@app.get("/api/v1/misconceptions", response_model=list[MisconceptionView])
def misconceptions():
    return _call(api.misconceptions)


@app.get("/api/v1/results")
def list_results() -> list[str]:
    return _call(api.list_results)


@app.get("/api/v1/results/{name}")
def read_results(name: str) -> dict:
    return _call(api.read_results, name)
