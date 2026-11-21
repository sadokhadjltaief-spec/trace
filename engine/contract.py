"""Frontend <-> engine contract (version below). Documented in docs/INTERFACE.md.

The frontend only ever receives these objects (as dicts via .model_dump()) from engine/api.py.
Changing a field = bump CONTRACT_VERSION and update docs/INTERFACE.md + docs/fixtures/.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.6"  # 1.1 explanation_evidence; 1.2 CourseAnswer; 1.3 sims; 1.4 game; 1.5 report; 1.6 chat

Lang = Literal["fr", "ar", "en"]
HypId = Literal["M0", "M1", "M2", "M3", "M4"]
TutorState = Literal["DIAGNOSE", "HINT_1", "HINT_2", "HINT_3", "RECONSTRUCT", "TRANSFER", "DONE", "HANDOFF"]
CheckName = Literal["leak", "congruency", "math", "style"]
CheckStatus = Literal["pass", "fail", "not_applicable"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- displayable text
class Check(_M):
    name: CheckName
    status: CheckStatus
    detail: str = ""


class SafeText(_M):
    """Every piece of text the frontend may display. Render ONLY if shown_allowed is true."""
    text: str
    lang: Lang = "en"
    origin: Literal["llm", "verified_bank", "template"]
    checks: list[Check]
    shown_allowed: bool
    fallback_used: bool = False  # true when the guards rejected the LLM text and a verified fallback was used

    @model_validator(mode="after")
    def _allowed_matches_checks(self):
        names = {c.name for c in self.checks}
        any_fail = any(c.status == "fail" for c in self.checks)
        all_four = {"leak", "congruency", "math", "style"} <= names
        expected = (not any_fail) and all_four
        if self.shown_allowed != expected:
            raise ValueError("shown_allowed must be true iff all four checks ran and none failed")
        return self


# ---------------------------------------------------------------- shared views
class MisconceptionView(_M):
    id: HypId
    name_en: str
    name_fr: str = ""
    name_ar: str = ""


class HypProb(_M):
    id: HypId
    name_en: str
    prob: float = Field(ge=0, le=1)


class QuestionView(_M):
    """A question as shown to the student. Never contains the answer key or option mappings."""
    id: str
    text: str                      # may contain LaTeX \\( ... \\)
    options: dict[str, str]        # letter -> option text (LaTeX allowed)
    requires_confidence: bool = True
    why_mode: Literal["free", "structured"] = "free"
    why_options: list[SafeText] = []  # only when why_mode == "structured"


class Agenda(_M):
    step: int
    total: int
    next: str                      # short label of what comes next (shown in clear mode)


class GuardEvent(_M):
    ts: float
    check: CheckName
    status: Literal["pass", "fail"]
    action: Literal["shown", "regenerated", "fallback"]
    summary: str                   # e.g. "1 hint blocked: revealed answer"


class Cost(_M):
    calls: int
    cached_calls: int
    prompt_tokens: int
    completion_tokens: int
    label: str                     # e.g. "free tier, rate-limited"


class AnswerRecord(_M):
    question_id: str
    option: str
    confidence: Literal["sure", "unsure"] | None
    correct: bool                  # graded by the answer key (deterministic)
    explanation: str | None = None


# ---------------------------------------------------------------- the five contract objects
class Alternative(_M):
    question_id: str
    ig_bits: float


class NextQuestion(_M):
    question_id: str | None
    ig_bits: float
    alternatives: list[Alternative]  # top 2 runners-up
    entropy_bits: float            # current posterior entropy
    stop: bool
    stop_reason: Literal["threshold", "max_questions", "no_questions"] | None


class SessionState(_M):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    student: dict                  # {"name": str, "level": str, "lang": Lang}
    profile: dict[str, bool | int | str]  # support-profile toggles (engine/profiles.yaml)
    demo_mode: bool
    state: TutorState
    agenda: Agenda
    posterior: list[HypProb]       # teacher/judge view; student view shows it only outside clear mode
    top: HypProb
    asked: list[AnswerRecord]
    current_question: QuestionView | None
    next_question: NextQuestion
    fragile: list[str]             # question ids answered right but "not sure"
    guard_events: list[GuardEvent]
    cost: Cost
    warnings: list[str] = []       # e.g. "bank not reviewed: unverified questions in use (dev mode)"


class Reconstruction(_M):
    """Find-the-mistake view: steps only; the error step index stays in the engine."""
    id: str
    problem: str
    steps: list[str]


class LabelProb(_M):
    id: Literal["M0", "M1", "M2", "M3", "M4", "other"]
    prob: float = Field(ge=0, le=1)


class ExplanationEvidence(_M):
    """What the explanation detector concluded (teacher/judge panel). Numbers come from engine code."""
    method: Literal["combined", "tfidf"]       # combined = TF-IDF + LLM few-shot ranking
    lang: Literal["en", "fr", "ar", "darija"]  # detected language of the student's text
    original: str
    english: str                               # translation used by the detector (== original if English)
    dist: list[LabelProb]                      # over M0..M4 + other
    notes: list[str] = []                      # e.g. "LLM detector unavailable; TF-IDF only"


class Grading(_M):
    correct: bool | None
    method: Literal["answer_key", "sympy", "simulation", "llm_rubric", "none"]
    label: str                     # UI must show it; "llm_rubric" must be labelled as LLM-graded


class TutorTurn(_M):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    turn_id: int
    state: TutorState              # decided by the state machine, not the LLM
    message: SafeText
    expects: Literal["answer", "retry", "error_step", "explanation", "transfer_answer", "none"]
    agenda: Agenda
    question: QuestionView | None = None
    reconstruction: Reconstruction | None = None
    grading: Grading
    posterior: list[HypProb]       # snapshot after this turn (teacher/judge panel)
    next_question: NextQuestion | None = None
    guard_events: list[GuardEvent] = []
    explanation_evidence: ExplanationEvidence | None = None  # since 1.1


class LessonRef(_M):
    file: str
    page: int
    snippet: str
    source_url: str | None = None


class CourseHit(_M):
    """One retrieved passage from the student's course files (extractive: the text is never rewritten)."""
    folder: str
    file: str
    page: int
    snippet: str
    lang: Literal["fr", "ar", "en", "darija"]
    source_url: str | None = None
    allow_derivatives: bool
    score: float


class CourseAnswer(_M):
    """Course Q&A (since 1.2). Extractive: `hits` ARE the answer, each with file + page. `found` is false when
    nothing relevant was retrieved; then show `note` and do not answer from memory."""
    contract_version: str = CONTRACT_VERSION
    query: str
    found: bool
    hits: list[CourseHit]
    note: str
    retrieval: str                 # e.g. "BM25 + intfloat/multilingual-e5-small (RRF)"


class Calibration(_M):
    sure_correct: int
    sure_total: int
    unsure_correct: int
    unsure_total: int


class SessionSummary(_M):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    diagnosis: HypProb
    diagnosis_names: MisconceptionView
    status: Literal["mastered", "in_progress", "handoff", "no_misconception"]
    evidence: list[str]            # human-readable evidence lines built by the engine
    tried: list[TutorState]
    outcome: SafeText
    next_step: SafeText
    lesson_refs: list[LessonRef]
    handoff_note: SafeText | None
    calibration: Calibration
    cost: Cost


class Source(_M):
    file: str
    page: int | None = None
    timestamp: str | None = None   # for video/audio sources


class OutputFile(_M):
    path: str                      # relative to the repo root, under exports/<session>/
    mime: str


class StudioOutput(_M):
    contract_version: str = CONTRACT_VERSION
    session_id: str
    tool: Literal["flashcards", "summary", "quiz", "slides", "pdf", "diagram", "mindmap", "video", "podcast"]
    targeted_at: MisconceptionView | None  # UI must print "Targeted at: <name>" when present
    sources: list[Source]
    files: list[OutputFile]
    items: list[dict]              # tool-specific; every text inside is a SafeText dict
    refused: str | None = None     # e.g. folder has allow_derivatives: false

    @model_validator(mode="after")
    def _refusal_has_no_output(self):
        if self.refused and (self.files or self.items):
            raise ValueError("a refused output carries no files or items")
        return self


# ---------------------------------------------------------------- simulations (since 1.3)
class SimSeries(_M):
    name: str                      # e.g. "height", "speed", "angle", "position"
    unit: str
    t: list[float]
    y: list[float]


class SimRun(_M):
    """A computed simulation (numpy/scipy). Plot `series`; show `result` values with `units`."""
    label: str = "a"               # "a" / "b" when two objects are compared
    template: Literal["free_fall", "pendulum", "cart_force"]
    params: dict
    units: dict[str, str]
    series: list[SimSeries]
    result: dict


class SimItemView(_M):
    """A Predict question (no correct answer inside: it is computed by the engine after the prediction)."""
    id: str
    template: Literal["free_fall", "pendulum", "cart_force"]
    text: str
    options: dict[str, str]
    runs_params: dict[str, dict]   # label -> parameters, to set the sliders / draw the setup
    transfer_of: str | None = None
    requires_confidence: bool = True


class SimTurn(_M):
    contract_version: str = CONTRACT_VERSION
    item_id: str
    stage: Literal["observe", "explain_saved", "transfer_result"]
    grading: Grading               # method "simulation": the prediction against the computed result
    observed: str                  # computed outcome, e.g. "same", "increases", "constant_speed"
    result_text: SafeText | None = None
    runs: list[SimRun] = []
    posterior: list[HypProb]       # PHYSICS posterior (ids M0..M4 = the physics bank's slots, names given)
    message: SafeText
    expects: Literal["explanation", "transfer_answer", "none"]
    next_item: SimItemView | None = None


# ---------------------------------------------------------------- game "Chasse aux erreurs" (since 1.4)
class GameRoundView(_M):
    round: int
    total: int
    item_id: str
    problem: str
    steps: list[str]               # numbered from 1; exactly one is wrong (the index stays in the engine)
    reasons: dict[str, str]        # letter -> misconception name (1 correct, 2 distractors)


class GameFeedback(_M):
    step_ok: bool
    reason_ok: bool
    correct_step: int
    correct_reason: str            # misconception name in the student's language
    points_gained: int


class GameTurn(_M):
    contract_version: str = CONTRACT_VERSION
    round: GameRoundView | None    # the next round (None when the game is over)
    feedback: GameFeedback | None  # about the round just answered
    points: int
    streak: int
    best_streak: int
    done: bool
    message: SafeText
    posterior: list[HypProb]       # maths posterior (a wrong reason is evidence)


class ReportExport(_M):
    """The one-page report as files (since 1.5): Markdown + PDF (with the calibration chart) in one language."""
    contract_version: str = CONTRACT_VERSION
    session_id: str
    lang: Lang
    files: list[OutputFile]


class ChatAnswer(_M):
    """Course chat ("Ask the tutor", since 1.6). Render `answer` only if shown_allowed; list `citations`."""
    contract_version: str = CONTRACT_VERSION
    question: str
    on_topic: bool
    method: Literal["rag_llm", "rag_extractive", "not_found", "refusal"]
    topic_reason: str              # keywords | course passage | llm judge | judge unavailable
    answer: SafeText
    citations: list[CourseHit]
