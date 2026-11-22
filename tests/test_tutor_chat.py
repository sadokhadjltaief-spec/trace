"""Personal tutor: accounts + saved preferences, prompt adapted to them, guards, learning memory, media (LLM mocked)."""
import json

import pytest
from fastapi.testclient import TestClient

from engine import llm, media, rag, students, tutor_chat
from server.main import app


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(students, "DB", tmp_path / "t.db")
    monkeypatch.setattr(media, "OUT", tmp_path / "media")
    monkeypatch.setattr(rag, "COURSES", tmp_path / "courses")
    (tmp_path / "courses").mkdir()
    monkeypatch.setattr(rag, "CACHE", tmp_path / "cache")
    rag.index(root=tmp_path / "courses", use_embeddings=False)


class FakeLLM:
    """Records the system prompts; answers tutor turns with `reply`, judge calls with 'no problem'."""

    def __init__(self, reply="Bonne question. Regardons un exemple : 2 + 3 = 5.", obs=None, media=None, image=None):
        self.systems, self.reply, self.obs, self.media, self.image = [], reply, obs or [], media, image

    def chat(self, req):
        self.systems.append(req.messages[0]["content"])
        data = {"reply": self.reply, "mode": "explain", "suggestions": ["Continuer", "Plus simple"],
                "observations": self.obs, "media": self.media, "uses_course": False}
        return llm.Response(json.dumps(data), data, "m", 1, 1, False, 0.0)

    def ask_json(self, system, user, *, purpose, **kw):
        if purpose == "media_image":
            return self.image or {"kind": "right_triangle", "title": "Pythagore", "caption": "c est calculé.", "a": 3, "b": 4}
        return {"texts": [{"id": "a", "congruent": [], "claims": []}]}


@pytest.fixture
def fake(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(llm, "chat", f.chat)
    monkeypatch.setattr(llm, "ask_json", f.ask_json)
    return f


def test_accounts_hash_passwords_and_keep_the_profile():
    r = students.register("Amira@Wasla.test", "motdepasse1", {"name": "Amira", "explanationStyle": "visual",
                                                                "learningEnvironment": "hacker"})
    assert r["email"] == "amira@wasla.test" and r["profile"] == {"name": "Amira", "explanationStyle": "visual"}
    with pytest.raises(students.AuthError, match="email_taken"):
        students.register("amira@wasla.test", "autremotdepasse")
    with pytest.raises(students.AuthError, match="bad_credentials"):
        students.login("amira@wasla.test", "mauvais123")
    with pytest.raises(students.AuthError, match="password_short"):
        students.register("b@wasla.test", "court")
    tok = students.login("amira@wasla.test", "motdepasse1")["token"]
    st = students.from_token(tok)
    students.save_profile(st["student_id"], {"informationAmount": "small"})
    assert students.from_token(tok)["profile"]["informationAmount"] == "small"
    with students._db() as c:
        assert "motdepasse1" not in json.dumps(c.execute("SELECT * FROM students").fetchall())


def test_the_prompt_follows_the_saved_preferences_and_changes_with_them(fake):
    tok = students.register("e@wasla.test", "motdepasse1", {"explanationStyle": "short", "informationAmount": "small",
                                                             "learningEnvironment": "calm", "questionTiming": "none"})["token"]
    st = students.from_token(tok)
    tutor_chat.turn("Explique les fractions", "fr", None, st)
    p1 = fake.systems[-1]
    assert "short and simple" in p1 and "small sections" in p1 and "minimal and calm" in p1 and "no time pressure" in p1
    students.save_profile(st["student_id"], {"explanationStyle": "examples", "informationAmount": "detailed",
                                             "learningEnvironment": "gamified", "questionTiming": "standard"})
    tutor_chat.turn("Explique les fractions", "fr", None, students.from_token(tok))
    p2 = fake.systems[-1]
    assert "examples first" in p2 and "AMOUNT: detailed" in p2 and "gamified" in p2 and "short and simple" not in p2


def test_reply_shown_only_after_guards_and_false_maths_falls_back(fake):
    r = tutor_chat.turn("Combien font 2 + 3 ?", "fr", None, None, {"learningEnvironment": "interactive"})
    assert r["reply"]["shown_allowed"] and r["mode"] == "explain" and r["suggestions"] == ["Continuer", "Plus simple"]
    fake.reply = "Donc 1/3 + 2/5 = 3/8."
    r = tutor_chat.turn("Et 1/3 + 2/5 ?", "fr", None, None, {})
    assert r["mode"] == "fallback" and "3/8" not in r["reply"]["text"] and r["reply"]["shown_allowed"]


def test_history_is_kept_and_memory_counts_only_answers(fake):
    st = students.from_token(students.register("m@wasla.test", "motdepasse1")["token"])
    fake.obs = [{"concept": "fractions", "subject": "maths", "status": "struggling", "note": "first question"}]
    r = tutor_chat.turn("C'est quoi une fraction ?", "fr", None, st)
    assert students.concepts(st["student_id"]) == []            # a first question shows nothing
    fake.obs = [{"concept": "fractions", "subject": "maths", "status": "understood", "note": "bonne réponse"}]
    r2 = tutor_chat.turn("C'est une part d'un tout", "fr", r["session_id"], st)
    assert r2["session_id"] == r["session_id"] and len(students.session_history(r["session_id"])) == 4
    c = students.concepts(st["student_id"])[0]
    assert c["understood"] == 1 and c["status"] == "in_progress"   # one exchange never decides "mastered"
    tutor_chat.turn("Oui, 3/4 c'est 3 parts sur 4", "fr", r["session_id"], st)
    assert students.concepts(st["student_id"])[0]["status"] == "mastered"
    p = students.progress(st["student_id"], "fr")
    assert p["counts"]["mastered"] == 1 and "fractions" in p["insight"]


def test_tidy_latex_and_emoji():
    assert tutor_chat.tidy(r"Bravo 🎉 $x^2 = \frac{1}{4}$") == "Bravo  x² = (1)/(4)"


def test_media_on_request_is_drawn_and_computed(fake):
    r = tutor_chat.turn("Dessine-moi un triangle rectangle de côtés 3 et 4", "fr", None, None, {})
    m = r["media"]
    assert m["ok"] and m["type"] == "image" and m["url"].endswith(".png")
    assert (media.OUT / m["url"].rsplit("/", 1)[1]).exists()
    fake.image = {"kind": "steps", "title": "x", "steps": ["1/3 + 2/5 = 3/8"]}      # false maths: never drawn
    r = tutor_chat.turn("Montre-moi un schéma des étapes", "fr", None, None, {})
    assert not r["media"]["ok"] and r["media"]["error"]


def test_specs_are_checked():
    assert media.check_spec(media.Spec(kind="function_plot", expressions=["x**2 - y"])) != []
    assert media.check_spec(media.Spec(kind="fraction_bars", fractions=["1/0"])) != []
    assert media.check_spec(media.Spec(kind="function_plot", expressions=["x**2-4*x+3"])) == []


def test_http_auth_profile_tutor_progress(fake):
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": "h@wasla.test", "password": "motdepasse1"})
    assert r.status_code == 200
    H = {"Authorization": "Bearer " + r.json()["token"]}
    assert c.post("/api/v1/auth/register", json={"email": "h@wasla.test", "password": "motdepasse1"}).status_code == 409
    assert c.post("/api/v1/auth/login", json={"email": "h@wasla.test", "password": "nope12345"}).status_code == 401
    assert c.put("/api/v1/students/me/profile", json={"profile": {"explanationStyle": "visual"}}, headers=H).json()[
        "profile"]["explanationStyle"] == "visual"
    t = c.post("/api/v1/tutor/chat", json={"message": "Bonjour, explique les fractions", "lang": "fr"}, headers=H).json()
    assert t["preferences_used"]["explanationStyle"] == "visual" and t["reply"]["shown_allowed"]
    assert c.get("/api/v1/students/me/progress", headers=H).status_code == 200
    assert c.get("/api/v1/students/me/progress").status_code == 401
    assert c.get("/api/v1/media/../../.env").status_code == 404


def test_opener_never_praises_a_wrong_answer_and_does_not_repeat():
    o = tutor_chat.choose_opener("Exactement, bravo !", "incorrect", "fr", [], "interactive", "normal")
    assert not tutor_chat._PRAISE_CORRECT.search(o) or "tentative" in o.lower() or "presque" in o.lower()
    assert tutor_chat.choose_opener("Bonne question !", "question", "fr", ["Bonne question !"], "interactive", "normal") \
        != "Bonne question !"
    calm = tutor_chat.choose_opener("Super question ! On y va.", "question", "fr", [], "calm", "normal")
    assert "!" not in calm
    assert len(tutor_chat.choose_opener("un " * 30, "question", "fr", [], "gamified", "small").split()) <= 10


def test_situation_from_message_and_model_judgement():
    assert tutor_chat.situation("Donne-moi la réponse", {}) == "answer"
    assert tutor_chat.situation("je comprends rien", {"student_answer": "none"}) == "frustrated"
    assert tutor_chat.situation("x = 3", {"student_answer": "incorrect"}) == "incorrect"
    assert tutor_chat.situation("x = 3", {"student_answer": "correct"}) == "correct"
    assert tutor_chat.situation("C'est quoi une dérivée ?", {}) == "question"


def test_every_reply_starts_with_the_opener(fake):
    fake.reply = "Une fraction représente une part d'un tout."
    r = tutor_chat.turn("C'est quoi une fraction ?", "fr", None, None, {"learningEnvironment": "interactive"})
    first = r["reply"]["text"].split("\n\n")[0]
    assert first in sum(tutor_chat.OPENERS["fr"].values(), []) and "part d'un tout" in r["reply"]["text"]


def test_video_failure_keeps_the_reply_and_the_tutor_knows_a_video_comes(fake, monkeypatch):
    seen = []
    chat = fake.chat
    monkeypatch.setattr(llm, "chat", lambda req: (seen.append(req.messages[-1]["content"]), chat(req))[1])

    def broken(*a, **k):  # e.g. ffmpeg cannot start: OSError [WinError 6] The handle is invalid
        raise OSError(6, "The handle is invalid")
    monkeypatch.setattr(media, "video", broken)
    r = tutor_chat.turn("expliquer equation second degre", "fr", None, None, {}, want_media="video")
    assert r["reply"]["text"] and r["media"]["type"] == "video" and not r["media"]["ok"] and r["media"]["error"]
    assert "Never say you cannot create videos" in seen[-1] and "narrated video" in seen[-1]
    assert "The handle is invalid" in (media.OUT / "errors.log").read_text(encoding="utf-8")
    tutor_chat.turn("Bonjour", "fr", None, None, {})
    assert "Never say you cannot create" not in seen[-1]          # ordinary turns: prompt unchanged (cache kept)
