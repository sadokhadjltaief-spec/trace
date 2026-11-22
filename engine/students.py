"""Student accounts, learning preferences and learning memory (SQLite, same file as the LLM log: .cache/trace.db).

- Accounts: email + password (PBKDF2-SHA256, 200k iterations, per-user salt). A login returns a random bearer token.
  Nothing here sends data anywhere; the database file is local and gitignored.
- Profile: name, level, language and the four onboarding preferences (explanations, information amount, learning
  environment, question timing) plus free notes. The tutor reads them at the start of every turn, so a change in the
  settings changes the next answer.
- Learning memory: per concept, how many times the student showed understanding, struggled or showed a possible
  misconception, and which explanation style helped. Status is computed by code from the counts: one exchange never
  decides it (see `concept_status`). No condition, diagnosis or ability is ever inferred or stored.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time

from engine import ROOT

DB = ROOT / ".cache" / "trace.db"
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PREF_VALUES = {
    "explanationStyle": {"step-by-step", "short", "examples", "visual"},
    "informationAmount": {"small", "normal", "detailed"},
    "learningEnvironment": {"calm", "interactive", "gamified"},
    "questionTiming": {"none", "flexible", "standard"},
}
PROFILE_KEYS = ("name", "educationLevel", "lang", "dailyGoal", "notes", *PREF_VALUES)


class AuthError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # email_invalid | password_short | email_taken | bad_credentials | bad_token


def _db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL,
        pw_hash TEXT NOT NULL, profile TEXT NOT NULL DEFAULT '{}', created REAL, updated REAL);
    CREATE TABLE IF NOT EXISTS auth_tokens (token TEXT PRIMARY KEY, student_id TEXT NOT NULL, created REAL);
    CREATE TABLE IF NOT EXISTS learner_concepts (student_id TEXT NOT NULL, concept TEXT NOT NULL, subject TEXT,
        understood INTEGER DEFAULT 0, struggling INTEGER DEFAULT 0, misconception INTEGER DEFAULT 0,
        last_status TEXT, last_note TEXT, helped_by TEXT, updated REAL, PRIMARY KEY (student_id, concept));
    CREATE TABLE IF NOT EXISTS tutor_sessions (id TEXT PRIMARY KEY, student_id TEXT, history TEXT NOT NULL,
        created REAL, updated REAL);
    """)
    return c


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()


def clean_profile(p: dict | None) -> dict:
    """Keep only known keys; preference values must be one of the onboarding options (anything else is dropped)."""
    p = p or {}
    out = {}
    for k in PROFILE_KEYS:
        if k not in p or p[k] is None:
            continue
        v = p[k]
        if k in PREF_VALUES:
            if v in PREF_VALUES[k]:
                out[k] = v
        elif k == "notes":
            out[k] = {str(a)[:40]: str(b)[:300] for a, b in (v or {}).items()} if isinstance(v, dict) else {}
        else:
            out[k] = str(v)[:80]
    return out


def register(email: str, password: str, profile: dict | None = None) -> dict:
    email = (email or "").strip().lower()
    if not EMAIL.match(email):
        raise AuthError("email_invalid")
    if len(password or "") < 8:
        raise AuthError("password_short")
    salt = secrets.token_hex(16)
    sid = "stu-" + secrets.token_hex(6)
    now = time.time()
    with _db() as c:
        if c.execute("SELECT 1 FROM students WHERE email=?", (email,)).fetchone():
            raise AuthError("email_taken")
        c.execute("INSERT INTO students VALUES (?,?,?,?,?,?,?)",
                  (sid, email, salt, _hash(password, salt), json.dumps(clean_profile(profile)), now, now))
    return login(email, password)


def login(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    with _db() as c:
        row = c.execute("SELECT id, salt, pw_hash, profile FROM students WHERE email=?", (email,)).fetchone()
        if not row or not hmac.compare_digest(_hash(password or "", row[1]), row[2]):
            raise AuthError("bad_credentials")
        token = secrets.token_urlsafe(32)
        c.execute("INSERT INTO auth_tokens VALUES (?,?,?)", (token, row[0], time.time()))
    return {"token": token, "student_id": row[0], "email": email, "profile": json.loads(row[3])}


def from_token(token: str | None) -> dict:
    if not token:
        raise AuthError("bad_token")
    with _db() as c:
        row = c.execute("SELECT s.id, s.email, s.profile FROM auth_tokens t JOIN students s ON s.id=t.student_id "
                        "WHERE t.token=?", (token,)).fetchone()
    if not row:
        raise AuthError("bad_token")
    return {"student_id": row[0], "email": row[1], "profile": json.loads(row[2])}


def logout(token: str) -> None:
    with _db() as c:
        c.execute("DELETE FROM auth_tokens WHERE token=?", (token,))


def save_profile(student_id: str, profile: dict) -> dict:
    with _db() as c:
        row = c.execute("SELECT profile FROM students WHERE id=?", (student_id,)).fetchone()
        if not row:
            raise KeyError(student_id)
        merged = {**json.loads(row[0]), **clean_profile(profile)}
        c.execute("UPDATE students SET profile=?, updated=? WHERE id=?", (json.dumps(merged), time.time(), student_id))
    return merged


# ---------------------------------------------------------------- learning memory
def _norm_concept(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:80]


def observe(student_id: str, observations: list[dict], helped_by: str | None = None) -> None:
    """Add the tutor's observations of this turn (understood / struggling / misconception) to the counts."""
    now = time.time()
    with _db() as c:
        for o in observations or []:
            if not isinstance(o, dict):
                continue
            concept, status = _norm_concept(o.get("concept")), str(o.get("status", ""))
            if not concept or status not in ("understood", "struggling", "misconception"):
                continue
            c.execute("INSERT OR IGNORE INTO learner_concepts (student_id, concept, subject, updated) VALUES (?,?,?,?)",
                      (student_id, concept, str(o.get("subject", ""))[:40], now))
            c.execute(f"UPDATE learner_concepts SET {status}={status}+1, last_status=?, last_note=?, updated=?, "
                      f"helped_by=COALESCE(?, helped_by) WHERE student_id=? AND concept=?",
                      (status, str(o.get("note", ""))[:200], now, helped_by if status == "understood" else None,
                       student_id, concept))


def concept_status(understood: int, struggling: int, misconception: int) -> str:
    """Computed, never decided by one exchange: 'mastered' needs 2+ signs of understanding and more of them than of
    difficulty; 'to_review' needs 2+ signs of difficulty; otherwise 'in_progress'."""
    trouble = struggling + misconception
    if understood >= 2 and understood > trouble:
        return "mastered"
    if trouble >= 2 and trouble >= understood:
        return "to_review"
    return "in_progress"


def concepts(student_id: str) -> list[dict]:
    with _db() as c:
        rows = c.execute("SELECT concept, subject, understood, struggling, misconception, last_status, last_note, "
                         "helped_by, updated FROM learner_concepts WHERE student_id=? ORDER BY updated DESC",
                         (student_id,)).fetchall()
    out = []
    for concept, subject, u, s, m, last, note, helped, upd in rows:
        total = u + s + m
        out.append({"concept": concept, "subject": subject or "", "understood": u, "struggling": s,
                    "misconception": m, "signals": total, "mastery": round(u / total, 3) if total else 0.0,
                    "status": concept_status(u, s, m), "last_status": last, "last_note": note or "",
                    "helped_by": helped or "", "updated": upd})
    return out


def memory_summary(student_id: str, k: int = 8) -> str:
    """Short text for the tutor prompt: what this student showed recently (counts, not judgements)."""
    rows = concepts(student_id)[:k]
    if not rows:
        return "(no previous observations)"
    return "\n".join(f"- {r['concept']}: {r['status']} (understood {r['understood']}, struggled {r['struggling']}, "
                     f"possible misconception {r['misconception']}){'; helped by ' + r['helped_by'] if r['helped_by'] else ''}"
                     f"{'; last note: ' + r['last_note'] if r['last_note'] else ''}" for r in rows)


# ---------------------------------------------------------------- tutor sessions (conversation history)
def session_history(session_id: str) -> list[dict]:
    with _db() as c:
        row = c.execute("SELECT history FROM tutor_sessions WHERE id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else []


def save_history(session_id: str, student_id: str | None, history: list[dict]) -> None:
    now = time.time()
    with _db() as c:
        c.execute("INSERT INTO tutor_sessions VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET history=excluded.history, "
                  "updated=excluded.updated", (session_id, student_id, json.dumps(history[-40:], ensure_ascii=False),
                                               now, now))


INSIGHT = {
    "fr": {"empty": "Pas encore de données : discute avec le tuteur et tes progrès apparaîtront ici.",
           "best": "Point fort : {c}.", "review": "À revoir en priorité : {c}.", "helped": "Ce qui t'aide le plus : {s}.",
           "start": "Continue : chaque échange ajoute un signal, aucune notion n'est jugée sur un seul échange."},
    "en": {"empty": "No data yet: chat with the tutor and your progress will appear here.",
           "best": "Strong point: {c}.", "review": "Review first: {c}.", "helped": "What helps you most: {s}.",
           "start": "Keep going: each exchange adds a signal, no notion is judged on a single exchange."},
    "ar": {"empty": "لا توجد بيانات بعد: تحدّث مع المعلّم وسيظهر تقدّمك هنا.",
           "best": "نقطة قوة: {c}.", "review": "راجع أولًا: {c}.", "helped": "ما يساعدك أكثر: {s}.",
           "start": "واصل: كل تبادل يضيف إشارة، ولا يُحكم على أي مفهوم من تبادل واحد."},
}
STYLE_NAMES = {"fr": {"step-by-step": "les explications étape par étape", "short": "les explications courtes",
                      "examples": "les exemples d'abord", "visual": "les explications visuelles"},
               "en": {"step-by-step": "step-by-step explanations", "short": "short explanations",
                      "examples": "examples first", "visual": "visual explanations"},
               "ar": {"step-by-step": "الشرح خطوة بخطوة", "short": "الشرح المختصر", "examples": "الأمثلة أولًا",
                      "visual": "الشرح المرئي"}}


def progress(student_id: str, lang: str = "fr") -> dict:
    """Learning memory as numbers + an insight sentence written by code (not the LLM)."""
    from collections import Counter
    lang = lang if lang in INSIGHT else "fr"
    rows = concepts(student_id)
    by_subject: dict[str, list[float]] = {}
    for r in rows:
        by_subject.setdefault(r["subject"] or "-", []).append(r["mastery"])
    counts = Counter(r["status"] for r in rows)
    with _db() as c:
        hist = [json.loads(h[0]) for h in c.execute("SELECT history FROM tutor_sessions WHERE student_id=?",
                                                    (student_id,)).fetchall()]
    T = INSIGHT[lang]
    if not rows:
        insight = T["empty"]
    else:
        parts = []
        best = [r for r in rows if r["status"] == "mastered"]
        review = sorted([r for r in rows if r["status"] == "to_review"], key=lambda r: r["mastery"])
        if best:
            parts.append(T["best"].format(c=max(best, key=lambda r: r["understood"])["concept"]))
        if review:
            parts.append(T["review"].format(c=review[0]["concept"]))
        helped = Counter(r["helped_by"] for r in rows if r["helped_by"])
        if helped:
            parts.append(T["helped"].format(s=STYLE_NAMES[lang].get(helped.most_common(1)[0][0], "")))
        insight = " ".join(parts) or T["start"]
    return {"concepts": rows, "by_subject": {k: round(sum(v) / len(v), 3) for k, v in by_subject.items()},
            "counts": {k: counts.get(k, 0) for k in ("mastered", "in_progress", "to_review")},
            "sessions": len(hist), "messages": sum(1 for h in hist for m in h if m.get("role") == "user"),
            "insight": insight}
