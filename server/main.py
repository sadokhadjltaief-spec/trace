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

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine import api
from engine.config import cfg
from engine.contract import (CONTRACT_VERSION, CourseAnswer, MisconceptionView, NextQuestion, SessionState,
                             SessionSummary, SimItemView, SimRun, SimTurn, StudioOutput, TutorTurn, GameTurn,
                             ReportExport, ChatAnswer, StudyPlan, PracticeCards, PracticeCheck, PracticeQuiz, PracticeSummary, Curriculum)

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
    from engine import llm
    return {"ok": True, "contract_version": CONTRACT_VERSION, "demo_mode": llm.demo_mode(),
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
def summary(sid: str, lang: Literal["fr", "ar", "en"] | None = None):
    return _call(api.summary, sid, lang)


@app.post("/api/v1/sessions/{sid}/report", response_model=ReportExport)
def report(sid: str, lang: Literal["fr", "ar", "en"] | None = None):
    return _call(api.report, sid, lang)


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


class SearchBody(BaseModel):
    query: str
    k: int = Field(default=3, ge=1, le=10)


@app.post("/api/v1/courses/index")
def course_index(refresh: bool = True) -> dict:
    return _call(api.course_index, refresh=refresh)


@app.post("/api/v1/courses/search", response_model=CourseAnswer)
def course_search(body: SearchBody):
    return _call(api.course_search, body.query, body.k)


UPLOAD_EXT = {".pdf", ".txt", ".md"}   # DOCX/PPTX: not supported yet (no parser installed)
UPLOAD_MAX_FILES, UPLOAD_MAX_BYTES = 10, 50 * 1024 * 1024


@app.post("/api/v1/courses/upload")
async def course_upload(files: list[UploadFile] = File(...)) -> dict:
    """Copy the student's own files into data/courses/uploads/ (allow_derivatives: true), then re-index.
    Limits: up to 10 files, 50 MB each, PDF / TXT / MD."""
    from pathlib import Path as _P

    from engine import rag
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(400, f"up to {UPLOAD_MAX_FILES} files")
    dest = rag.COURSES / "uploads"
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = _P(f.filename or "").name
        if _P(name).suffix.lower() not in UPLOAD_EXT:
            raise HTTPException(400, f"{name}: only PDF, TXT and MD files are accepted")
        data = await f.read()
        if len(data) > UPLOAD_MAX_BYTES:
            raise HTTPException(400, f"{name}: larger than 50 MB")
        (dest / name).write_bytes(data)
        saved.append(name)
    return {"saved": saved, "index": _call(api.course_index, refresh=True)}


class SimRunBody(BaseModel):
    template: str
    params: dict = Field(default_factory=dict)


class SimPredictBody(BaseModel):
    option: str
    confidence: Literal["sure", "unsure"]


class SimExplainBody(BaseModel):
    text: str | None = None


@app.get("/api/v1/sims/templates")
def sim_templates() -> dict:
    return _call(api.sim_templates)


@app.post("/api/v1/sims/run", response_model=SimRun)
def sim_run(body: SimRunBody):
    return _call(api.sim_run, body.template, body.params)


@app.get("/api/v1/sessions/{sid}/sims", response_model=list[SimItemView])
def sim_items(sid: str):
    return _call(api.sim_items, sid)


@app.post("/api/v1/sessions/{sid}/sims/{item_id}/predict", response_model=SimTurn)
def sim_predict(sid: str, item_id: str, body: SimPredictBody):
    return _call(api.sim_predict, sid, item_id, body.option, body.confidence)


@app.post("/api/v1/sessions/{sid}/sims/{item_id}/explain", response_model=SimTurn)
def sim_explain(sid: str, item_id: str, body: SimExplainBody):
    return _call(api.sim_explain, sid, item_id, body.text)


class GameAnswerBody(BaseModel):
    step: int
    reason: str


@app.post("/api/v1/sessions/{sid}/game", response_model=GameTurn)
def game_start(sid: str):
    return _call(api.game_start, sid)


@app.post("/api/v1/sessions/{sid}/game/answer", response_model=GameTurn)
def game_answer(sid: str, body: GameAnswerBody):
    return _call(api.game_answer, sid, body.step, body.reason)


class CardVerifyBody(BaseModel):
    ok: bool


class CardReviewBody(BaseModel):
    rating: Literal["again", "hard", "good", "easy"]


@app.get("/api/v1/sessions/{sid}/cards")
def studio_cards(sid: str, verified_only: bool = False) -> list[dict]:
    return _call(api.studio_cards, sid, verified_only)


@app.post("/api/v1/cards/{card_id}/verify")
def studio_card_verify(card_id: str, body: CardVerifyBody) -> dict:
    return _call(api.studio_card_verify, card_id, body.ok)


@app.post("/api/v1/sessions/{sid}/cards/{card_id}/review")
def studio_card_review(sid: str, card_id: str, body: CardReviewBody) -> dict:
    return _call(api.studio_card_review, sid, card_id, body.rating)


@app.get("/api/v1/exports/{sid}/{name}")
def export_file(sid: str, name: str):
    """Download a generated file (exports/<session>/<name>)."""
    import re as _re

    from fastapi.responses import FileResponse

    from engine.studio import EXPORTS
    if not (_re.fullmatch(r"[0-9a-f]{12}", sid) and _re.fullmatch(r"[\w.-]+", name)):
        raise HTTPException(400, "bad path")
    p = EXPORTS / sid / name
    if not p.is_file():
        raise HTTPException(404, "no such file")
    return FileResponse(p)


class ChatBody(BaseModel):
    question: str
    lang: Literal["fr", "ar", "en"] = "fr"
    session_id: str | None = None


@app.post("/api/v1/chat", response_model=ChatAnswer)
def chat(body: ChatBody):
    """Ask the tutor: course questions answered from the course files with citations; off-topic refused."""
    return _call(api.ask, body.question, body.lang, body.session_id)


@app.post("/api/v1/study-plan", response_model=StudyPlan)
async def study_plan(files: list[UploadFile] = File(...), details: str = Form(""),
                     lang: Literal["fr", "ar", "en"] = Form("fr"), session_id: str | None = Form(None)):
    """Study plan from the student's uploaded files (up to 10 files, 50 MB each, PDF / TXT / MD)."""
    if len(files) > UPLOAD_MAX_FILES:
        raise HTTPException(400, f"up to {UPLOAD_MAX_FILES} files")
    data = []
    for f in files:
        b = await f.read()
        if len(b) > UPLOAD_MAX_BYTES:
            raise HTTPException(400, f"{f.filename}: larger than 50 MB")
        data.append((f.filename or "file", b))
    return _call(api.study_plan, data, details, lang, session_id)


async def _read_files(files: list[UploadFile] | None) -> list[tuple[str, bytes]]:
    data = []
    for f in files or []:
        b = await f.read()
        if len(b) > UPLOAD_MAX_BYTES:
            raise HTTPException(400, f"{f.filename}: larger than 50 MB")
        data.append((f.filename or "file", b))
    if len(data) > UPLOAD_MAX_FILES:
        raise HTTPException(400, f"up to {UPLOAD_MAX_FILES} files")
    return data


@app.post("/api/v1/practice/quiz", response_model=PracticeQuiz)
async def practice_quiz(files: list[UploadFile] | None = File(None), text: str = Form(""), source: str = Form("file"),
                        details: str = Form(""), lang: Literal["fr", "ar", "en"] = Form("fr"),
                        session_id: str | None = Form(None)):
    return _call(api.practice_quiz, await _read_files(files), text, source, details, lang, session_id)


class PracticeCheckBody(BaseModel):
    question_id: str
    option: str


@app.post("/api/v1/practice/quiz/{quiz_id}/check", response_model=PracticeCheck)
def practice_check(quiz_id: str, body: PracticeCheckBody):
    return _call(api.practice_check, quiz_id, body.question_id, body.option)


@app.post("/api/v1/practice/cards", response_model=PracticeCards)
async def practice_cards(files: list[UploadFile] | None = File(None), text: str = Form(""), source: str = Form("file"),
                         details: str = Form(""), lang: Literal["fr", "ar", "en"] = Form("fr"),
                         session_id: str | None = Form(None)):
    return _call(api.practice_cards, await _read_files(files), text, source, details, lang, session_id)


@app.get("/api/v1/curriculum", response_model=Curriculum)
def curriculum(level: str | None = None):
    return _call(api.curriculum, level)


@app.post("/api/v1/practice/summary", response_model=PracticeSummary)
async def practice_summary(files: list[UploadFile] | None = File(None), text: str = Form(""), source: str = Form("file"),
                           focus: str = Form(""), pages: int = Form(2), lang: Literal["fr", "ar", "en"] = Form("fr"),
                           session_id: str | None = Form(None)):
    return _call(api.practice_summary, await _read_files(files), text, source, focus, pages, lang, session_id)
