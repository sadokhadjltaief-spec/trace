"""Write docs/fixtures/*.json: FAKE example objects for the frontend, built with the contract models.

Only MAP question text (MIT) and our own wording; no Eedi text. Numbers here are FAKE and must never be
shown as results (real numbers live in results/*.json).
Usage: .\\.venv\\Scripts\\python.exe scripts\\make_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT  # noqa: E402
from engine import safetext  # noqa: E402
from engine.contract import (Agenda, AnswerRecord, Calibration, Check, Cost, CourseAnswer, CourseHit,  # noqa: E402
                             ExplanationEvidence, SimItemView, SimRun, SimTurn, GameFeedback, GameRoundView, GameTurn,
                             GuardEvent, Grading, HypProb, LabelProb,
                             LessonRef, MisconceptionView, NextQuestion, OutputFile, QuestionView, Reconstruction,
                             SessionState, SessionSummary, Source, StudioOutput, TutorTurn)

SID = "fake0000demo"
N = {"M0": "No misconception found (none of M1-M4)", "M1": "Adds numerators and adds denominators",
     "M2": "Multiplies both numerator and denominator by the whole number",
     "M3": "Thinks 'two negatives make a positive' always applies",
     "M4": "Makes equivalent fractions by adding instead of multiplying"}
POST = {"M0": 0.08, "M1": 0.71, "M2": 0.07, "M3": 0.06, "M4": 0.08}


def post():
    return [HypProb(id=h, name_en=N[h], prob=p) for h, p in POST.items()]


Q1 = QuestionView(id="Q1", text=r"\( \frac{1}{3}+\frac{2}{5}= \)",
                  options={"A": r"\( \frac{3}{15} \)", "B": r"\( \frac{11}{30} \)", "C": r"\( \frac{3}{8} \)",
                           "D": r"\( \frac{11}{15} \)"})
Q5 = QuestionView(id="Q5", text=r"Calculate \( \frac{2}{3} \times 5 \)",
                  options={"A": r"\( \frac{2}{15} \)", "B": r"\( \frac{10}{15} \)", "C": r"\( 3 \frac{1}{3} \)",
                           "D": r"\( 5 \frac{2}{3} \)"})
NQ = NextQuestion(question_id="Q5", ig_bits=0.412, alternatives=[{"question_id": "Q11", "ig_bits": 0.398},
                                                                 {"question_id": "Q8", "ig_bits": 0.371}],
                  entropy_bits=1.402, stop=False, stop_reason=None)
COST = Cost(calls=6, cached_calls=2, prompt_tokens=3120, completion_tokens=640, label="free tier, rate-limited")
GE = [GuardEvent(ts=1700000000.0, check="leak", status="fail", action="regenerated",
                 summary="1 hint blocked: revealed answer")]
MV = MisconceptionView(id="M1", name_en=N["M1"], name_fr="Additionne les numérateurs et additionne les dénominateurs",
                       name_ar="يضيف البسط ويضيف المقام")
OK = [{"name": n, "status": "pass", "detail": "FAKE"} for n in ("leak", "congruency", "math", "style")]


def llm_text(t):
    return safetext.from_guards(t, [Check(**c) for c in OK])


state = SessionState(session_id=SID, student={"name": "Amira", "level": "7e", "lang": "fr"},
                     profile={"literal_language": False, "visible_agenda": True}, demo_mode=True, state="DIAGNOSE",
                     agenda=Agenda(step=2, total=5, next="next question"), posterior=post(),
                     top=HypProb(id="M1", name_en=N["M1"], prob=0.71),
                     asked=[AnswerRecord(question_id="Q1", option="C", confidence="sure", correct=False,
                                         explanation="1+2 is 3 and 3+5 is 8")],
                     current_question=Q5, next_question=NQ, fragile=[], guard_events=GE, cost=COST,
                     warnings=["FAKE DATA (docs/fixtures)"])

turn = TutorTurn(session_id=SID, turn_id=3, state="HINT_1",
                 message=llm_text("Look at the bottom numbers. What does the 3 in 1/3 tell you about the pieces?"),
                 expects="retry", agenda=Agenda(step=3, total=7, next="you try the question again"), question=Q1,
                 grading=Grading(correct=False, method="answer_key", label="Checked against the answer key"),
                 posterior=post(), next_question=None, guard_events=GE,
                 explanation_evidence=ExplanationEvidence(
                     method="combined", lang="fr", original="j'ai fait 1+2=3 et 3+5=8",
                     english="I did 1+2=3 and 3+5=8",
                     dist=[LabelProb(id=k, prob=v) for k, v in
                           {"M0": 0.05, "M1": 0.82, "M2": 0.03, "M3": 0.02, "M4": 0.03, "other": 0.05}.items()]))

turn_recon = TutorTurn(session_id=SID, turn_id=6, state="RECONSTRUCT",
                       message=llm_text("Here is a worked solution with one wrong step. Which step is wrong?"),
                       expects="error_step", agenda=Agenda(step=6, total=7, next="a new question"),
                       reconstruction=Reconstruction(id="R_M1_1", problem="Add the fractions 2/3 and 1/4.",
                                                     steps=["2/3 + 1/4 = 8/12 + 3/12", "8/12 + 3/12 = 11/24",
                                                            "The answer is 11/24."]),
                       grading=Grading(correct=None, method="none", label="Not graded yet"), posterior=post())

summ = SessionSummary(session_id=SID, diagnosis=HypProb(id="M1", name_en=N["M1"], prob=0.91), diagnosis_names=MV,
                      status="mastered",
                      evidence=["Q1: chose 3/8 (sure), explanation '1+2 is 3 and 3+5 is 8'",
                                "Q2: chose 3/12 (sure)"],
                      tried=["DIAGNOSE", "HINT_1", "HINT_2", "RECONSTRUCT", "TRANSFER", "DONE"],
                      outcome=safetext.static("The student found the wrong step and solved a new question correctly."),
                      next_step=safetext.static("Practise adding fractions with different denominators."),
                      lesson_refs=[LessonRef(file="my_notes/fractions.pdf", page=3,
                                             snippet="To add fractions, first use a common denominator.")],
                      handoff_note=None,
                      calibration=Calibration(sure_correct=1, sure_total=3, unsure_correct=1, unsure_total=1),
                      cost=COST)

card = {"front": llm_text("What is 1/2 + 1/2?").model_dump(),
        "back": llm_text("1/2 + 1/2 = 1. Adding the bottoms would give 2/4, which is only one half.").model_dump(),
        "verified": True, "misconception": "M1"}
studio = StudioOutput(session_id=SID, tool="flashcards", targeted_at=MV,
                      sources=[Source(file="my_notes/fractions.pdf", page=3)],
                      files=[OutputFile(path=f"exports/{SID}/flashcards.apkg", mime="application/octet-stream"),
                             OutputFile(path=f"exports/{SID}/flashcards.tsv", mime="text/tab-separated-values")],
                      items=[card])
refused = StudioOutput(session_id=SID, tool="summary", targeted_at=MV, sources=[], files=[], items=[],
                       refused="This folder does not allow derived material (allow_derivatives: false).")

course = CourseAnswer(query="additionner deux fractions", found=True,
                      note="Passages copied from your course files (not rewritten). Check the page cited.",
                      retrieval="BM25 + intfloat/multilingual-e5-small (reciprocal rank fusion)",
                      hits=[CourseHit(folder="mes_notes", file="mes_notes/fractions.pdf", page=3, lang="fr",
                                      snippet="Pour additionner deux fractions, on les met d'abord au même dénominateur…",
                                      source_url=None, allow_derivatives=True, score=0.03252)])
course_none = CourseAnswer(query="photosynthèse", found=False, hits=[],
                           note="Nothing relevant was found in your course files. TRACE does not answer from memory.",
                           retrieval="BM25 + intfloat/multilingual-e5-small (reciprocal rank fusion)")

from engine import sims as _sims  # noqa: E402  (real computed physics; only the posterior below is FAKE)
_runs = [SimRun(label=k, **_sims.run("free_fall", {"mass_kg": m, "height_m": 20})) for k, m in (("a", 1), ("b", 5))]
sim_item = SimItemView(id="S1", template="free_fall", text="Deux boules de même taille sont lâchées en même temps…",
                       options={"A": "La boule b (5 kg)", "B": "La boule a (1 kg)", "C": "Les deux en même temps"},
                       runs_params={"a": {"mass_kg": 1, "height_m": 20}, "b": {"mass_kg": 5, "height_m": 20}})
sim_turn = SimTurn(item_id="S1", stage="observe", observed="same",
                   grading=Grading(correct=False, method="simulation", label="Vérifié avec la simulation calculée"),
                   result_text=safetext.static("Boule a : 2.0193 s. Boule b : 2.0193 s.", lang="fr"), runs=_runs,
                   posterior=[HypProb(id=h, name_en=n, prob=p) for h, n, p in (
                       ("M0", "No physics misconception found", 0.1), ("M1", "Thinks heavier objects always fall faster", 0.6),
                       ("M2", "Thinks a pendulum's period depends on its mass", 0.1),
                       ("M3", "Thinks a constant force gives a constant speed", 0.1),
                       ("M4", "Thinks an object stops as soon as the force stops", 0.1))],
                   message=safetext.static("Regarde la simulation. Compare le résultat avec ta prédiction.", lang="fr"),
                   expects="explanation")

game_turn = GameTurn(round=GameRoundView(round=2, total=5, item_id="R_M1_1", problem="Additionne les fractions 2/3 et 1/4.",
                                         steps=["Mettre chaque fraction au dénominateur 12 : 2/3 = 8/12 et 1/4 = 3/12.",
                                                "Additionner les numérateurs et les dénominateurs : 8/12 + 3/12 = 11/24.",
                                                "Écrire le résultat sous forme de fraction."],
                                         reasons={"A": "Additionne les numérateurs et additionne les dénominateurs",
                                                  "B": "Multiplie le numérateur et le dénominateur par le nombre entier",
                                                  "C": "Pense que « moins par moins » donne toujours plus"}),
                     feedback=GameFeedback(step_ok=True, reason_ok=True, correct_step=3, correct_reason="(FAKE)",
                                           points_gained=15),
                     points=15, streak=1, best_streak=1, done=False,
                     message=safetext.static("Bonne ligne et bonne raison. Trouve la ligne fausse. Puis choisis la raison.", lang="fr"),
                     posterior=post())

OUT = ROOT / "docs" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
for name, obj in {"session_state": state, "tutor_turn": turn, "tutor_turn_reconstruct": turn_recon,
                  "next_question": NQ, "session_summary": summ, "studio_output": studio,
                  "studio_output_refused": refused, "course_answer": course, "course_answer_none": course_none,
                  "sim_item": sim_item, "sim_turn": sim_turn,
                  "game_turn": game_turn}.items():
    (OUT / f"{name}.json").write_text(json.dumps(obj.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", f"docs/fixtures/{name}.json")

# JSON Schema for each contract object (for the frontend teammate / editor tooling)
SCH = ROOT / "docs" / "schema"
SCH.mkdir(parents=True, exist_ok=True)
for model in (SessionState, TutorTurn, NextQuestion, SessionSummary, StudioOutput, CourseAnswer, SimItemView, SimTurn, GameTurn):
    (SCH / f"{model.__name__}.json").write_text(json.dumps(model.model_json_schema(), indent=1), encoding="utf-8")
    print("wrote", f"docs/schema/{model.__name__}.json")
