"""Personal tutor chat (WASLA "AI tutor"): a guided, Socratic-style conversation adapted to each student.

Every turn:
1. Reads the student's saved onboarding preferences (engine/students.py; a change in the settings changes the next
   answer), the session history, what the student showed earlier (learning memory) and the course passages that match
   the message (the student's uploaded files first).
2. Builds the system prompt from those preferences (no single hard-coded teaching style).
3. Asks the LLM for a JSON turn: the reply (Markdown), its teaching move, up to 3 follow-up buttons, what the reply
   shows about the student's understanding (observations) and, when useful or asked, an image / video request.
4. Checks the reply with the guards (SymPy math check, congruency with possible misconceptions, language, style rules
   of the chosen environment). On failure: one regeneration with the reasons, then a safe, honest fallback.
5. Saves the history and adds the observations to the learning memory (counts; status computed by code).
The LLM never produces probabilities or grades; it never diagnoses a condition.
"""
from __future__ import annotations

import json
import re
import secrets

from engine import guards, llm, rag, safetext, students
from engine.contract import ChatMedia, TutorChatTurn
from engine.i18n import lang_of

LANG = {"fr": "French (address the student as \"tu\")", "ar": "Modern Standard Arabic (Arabic script; maths stays left to "
        "right with digits)", "en": "English"}

EXPLAIN = {
    "step-by-step": """EXPLANATION STYLE: step by step.
- Break the idea into small numbered steps; one idea at a time; never several hard ideas in the same message.
- After an important step, ask ONE small question and wait for the answer before going on (when it makes sense).""",
    "short": """EXPLANATION STYLE: short and simple.
- Clear everyday words, short sentences, only the essential point. Introduce a technical word only when needed and
  explain it the first time. Keep the message brief.""",
    "examples": """EXPLANATION STYLE: examples first.
- Start with a concrete example or a familiar real-life situation, then link it to the school concept, and only then
  state the general rule.""",
    "visual": """EXPLANATION STYLE: visual.
- Structure the answer visually: labelled steps, a small Markdown table, an equation on its own line, arrows (→) for
  processes. Avoid long paragraphs. When a picture would really help, request a diagram in "media" (type image).""",
}
AMOUNT = {
    "small": """AMOUNT: small sections. Give ONE short section (about 60 words) per message, then check understanding.
Always offer a "continue" follow-up button.""",
    "normal": "AMOUNT: normal sections. A balanced explanation (about 120 words) with an example or a short question.",
    "detailed": """AMOUNT: detailed. Complete explanation (up to about 280 words) organised with short Markdown headings:
reasoning, example, important details and relevant exceptions.""",
}
ENV = {
    "calm": """ENVIRONMENT: minimal and calm. Calm, neutral tone; no emoji; no exclamation marks; simple formatting; at most
one question per message.""",
    "interactive": """ENVIRONMENT: interactive. Invite participation: small questions, mini-challenges ("try this one"),
examples to complete. Still at most two questions in a message.""",
    "gamified": """ENVIRONMENT: gamified. Offer small challenges ("Mini-défi"), celebrate genuine progress with short
encouraging words (not childish, no emoji: the app shows the badges). Never invent points or scores in the text: the
app counts them.""",
}
TIMING = {
    "none": "PACE: no time pressure. Never mention time, speed or countdowns; a slow answer never means a lack of understanding.",
    "flexible": "PACE: flexible. No time limits; the student controls the pace.",
    "standard": "PACE: standard. Normal pace; do not mention timers in learning conversations.",
}
SUGG = {"fr": "Continuer / Plus simple / Un autre exemple / Donne-moi la réponse",
        "en": "Continue / Simpler please / Another example / Give me the answer",
        "ar": "تابع / أبسط من فضلك / مثال آخر / أعطني الإجابة"}
# onboarding ids as the frontend shows them: "lycee" is labelled Collège (7e-9e) and "college" Lycée (secondary)
LEVELS = {"school": "primary school", "lycee": "middle school (collège, 7th-9th grade)",
          "college": "high school (lycée, secondary)", "university": "university"}
DEFAULTS = {"explanationStyle": "step-by-step", "informationAmount": "normal", "learningEnvironment": "interactive",
            "questionTiming": "flexible"}

SYSTEM = """You are WASLA, a warm, patient personal tutor for a school student{name_part}{level_part}. Write in {lang}.

PERSONALITY: friendly, patient and encouraging, like a supportive personal tutor - never robotic, cold or formal, and
never childish. Every answer starts with a SHORT encouraging phrase ("opener"), written for THIS message:
- a question: welcome it ("Great question! Let's explore it together.");
- a correct answer: acknowledge the understanding and invite further ("Exactly! You're making a great connection.");
- a wrong or partly wrong answer: value the effort, NEVER congratulate it as correct ("Nice attempt! There's just one
  little thing to clarify.");
- frustration or discouragement: reassure first, then simplify ("No worries at all, this one is tricky at first.");
- a request for the direct answer: agree simply ("Of course! Here it is, with a short why.");
- a simple factual question: a very short opener (3-6 words).
Vary the opener; never reuse one of these recent openers: {recent_openers}. The opener never replaces the explanation.

PHILOSOPHY: do not just give answers; help the student understand how to find them (guided, Socratic-style), while
staying natural and conversational - never an interrogation.
Each turn: understand the request; decide what the student needs now (explanation, hint, example, guided question,
check of understanding, or the answer); build understanding progressively from the student's own words.
- Wrong or partly wrong answer: say what is reasonable in it, look for the cause, ask ONE targeted question or give a
  simpler explanation / another example, then check again. One mistake does not prove a misconception.
- Do not ask a question after every sentence: sometimes the student needs a clear explanation.
- If the student explicitly asks for the direct answer: you may first offer to work it out together in one sentence,
  but if they ask again (or clearly insist), give the answer clearly, with a short why. Never withhold it endlessly.
- If the student is stuck or asks for simpler words, a repetition or another example, give it without judgement.
- Never shame, never rush, never mention diagnoses or conditions (autism, ADHD, dyslexia...) and never guess them.
- Maths: plain text with Unicode (x², √, ≤, π, Δ) and simple Markdown, never LaTeX or $...$; every equality you
  write must be true; write equations as complete lines (e.g. "2x² - 4x - 6 = 0").
- Only school learning topics (any subject). For unrelated or unsafe requests, kindly say you can only help with
  learning, and set "mode" to "refusal".

THIS STUDENT'S PREFERENCES (follow them; they change how you teach, not what is true):
{prefs}

WHAT THIS STUDENT SHOWED BEFORE (counts from earlier turns; use it to adapt, do not treat it as permanent):
{memory}

COURSE MATERIAL:
{course}

MEDIA: the app can draw an educational diagram (computed, not a photo) or make a short narrated video. Request one in
"media" only when the student asks for a picture / diagram / video, or (visual style) when a diagram truly helps.
Video only when the student asks for a video. "request" = what to show, precisely, in one sentence.

Return JSON only:
{{"opener": "the short encouraging first sentence (not repeated in reply)",
 "reply": "Markdown message to the student, after the opener",
 "student_answer": "correct|partly_correct|incorrect|none (judge ONLY the student's last message; none if it is not an answer)",
 "student_mood": "neutral|frustrated|confident",
 "mode": "explain|hint|example|guided_question|answer|check|encourage|refusal",
 "suggestions": ["up to 3 short follow-up buttons the student may click, written in {lang_name}, e.g. {sugg}"],
 "observations": [{{"concept": "short concept name in the student's language", "subject": "maths|physics|history|...",
   "status": "understood|struggling|misconception", "note": "what the student's message shows, 10 words"}}],
 "media": null or {{"type": "image|video", "request": "..."}},
 "uses_course": true|false}}
Observations: only about what the STUDENT's last message shows (none if it shows nothing, e.g. a first question)."""

_MEDIA_ASK = re.compile(
    r"(?i)\b(dessine\w*|sch[ée]ma\w*|image\w*|illustr\w*|graphique\w*|courbe|diagramme\w*|figure|vid[ée]o\w*|"
    r"montre[- ]moi|draw|diagram|picture|image|graph|chart|video|show me|"
    r"ارسم|رسم|صورة|مخطط|فيديو|أرني)\b|رسم|فيديو|صورة")
_VIDEO_ASK = re.compile(r"(?i)vid[ée]o|فيديو")


_SUP = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")


def tidy(text: str) -> str:
    """Deterministic clean-up before the checks (the meaning is unchanged): real line breaks, LaTeX written as readable
    Unicode (the chat shows Markdown, not LaTeX), no emoji (the app shows badges itself)."""
    from engine.style import _EMOJI
    t = text.replace("\\n", "\n")
    for _ in range(3):
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", t)
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", t)
    t = re.sub(r"\^\{?([0-9n+\-]{1,3})\}?", lambda m: m.group(1).translate(_SUP), t)
    for a, b in ((r"\cdot", "·"), (r"\times", "×"), (r"\div", "÷"), (r"\pm", "±"), (r"\leq", "≤"), (r"\geq", "≥"),
                 (r"\neq", "≠"), (r"\Delta", "Δ"), (r"\pi", "π"), (r"\infty", "∞"), (r"\approx", "≈"), (r"\le", "≤"),
                 (r"\ge", "≥"), (r"\to", "→"), (r"\quad", " "), (r"\,", " "), (r"\left", ""), (r"\right", "")):
        t = t.replace(a, b)
    t = re.sub(r"\$\$\s*(.+?)\s*\$\$", r"\n\1\n", t, flags=re.S)
    t = re.sub(r"\$([^$\n]+)\$", r"\1", t)
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\\[\s*(.+?)\s*\\\]", r"\n\1\n", t, flags=re.S)       # \[ ... \]  display maths
    t = re.sub(r"\\\(\s*(.+?)\s*\\\)", r"\1", t, flags=re.S)           # \( ... \)  inline maths
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)                            # x_{1,2} -> x_1,2
    t = re.sub(r"[ \t]*\\\\?[ \t]*$", "", t, flags=re.M)               # LaTeX line breaks at line ends
    t = re.sub(r"(\d)️?⃣", r"\1.", t)                         # keycap emoji 1️⃣ -> "1."
    t = _EMOJI.sub("", t).replace("️", "")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _json(text: str) -> dict:
    """The model's JSON turn; a reply written as plain text (no JSON) is still usable as the reply."""
    t = (text or "").strip()
    for attempt in range(2):
        try:
            d = llm._parse_json(t)
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            if attempt:
                break
            # LaTeX inside the JSON strings (\( \frac \times ...) is not valid JSON: escape those backslashes
            t = re.sub(r"\\(?=(?:d?frac|tfrac|times|text|theta|tau|to|neq|ne|nu|beta|binom|right|rho|rangle|bar|"
                       r"underline|approx|top)(?![a-zA-Z]))", r"\\\\", t)
            t = re.sub(r'\\(?![\\/"bfnrtu])', r"\\\\", t)
    raw = (text or "").strip()
    m = re.search(r'"reply"\s*:\s*"(.*?)"\s*,\s*"mode"', raw, flags=re.S)     # last resort: the reply field alone
    if m:
        return {"reply": m.group(1).replace("\\n", "\n").replace('\\"', '"'), "mode": "explain"}
    return {"reply": raw, "mode": "explain"} if raw and "{" not in raw[:5] else {}


# ---------------------------------------------------------------- encouraging opener (checked by code)
# fallbacks when the model's opener is missing, repeated, too long or wrong for the situation; calm = no "!"
OPENERS = {
    "fr": {"question": ["Bonne question ! Explorons-la ensemble.", "Très bonne question, on regarde ça ensemble.",
                        "Super, c'est une question intéressante.", "Allons-y pas à pas."],
           "correct": ["Exactement ! Tu fais le bon lien.", "Bien vu, tu as compris l'idée.",
                       "C'est juste ! Allons un peu plus loin.", "Excellent raisonnement !"],
           "incorrect": ["Bonne tentative ! Il y a juste un détail à clarifier.", "Tu es sur une piste, regardons un point ensemble.",
                         "Pas grave, c'est comme ça qu'on apprend.", "Presque ! Regardons-le sous un autre angle."],
           "frustrated": ["Pas d'inquiétude, on va y arriver ensemble.", "Ne lâche rien, cette notion est difficile au début.",
                          "Prends ton temps, il n'y a aucune urgence.", "C'est normal de bloquer ici, on simplifie."],
           "answer": ["Bien sûr ! Voici la réponse, avec un court pourquoi.", "D'accord, voici la réponse expliquée."]},
    "en": {"question": ["Great question! Let's explore it together.", "Good question, let's look at it together.",
                        "Nice, that's an interesting question.", "Let's take it step by step."],
           "correct": ["Exactly! You're making a great connection.", "Well spotted, you've got the idea.",
                       "That's right! Let's take it one step further.", "Excellent thinking!"],
           "incorrect": ["Nice attempt! There's just one little thing to clarify.", "You're on a track, let's check one point together.",
                         "No problem, that's how we learn.", "Almost! Let's look at it from another angle."],
           "frustrated": ["Don't worry, we'll figure it out together.", "Don't give up, this idea is tricky at first.",
                          "Take your time, there's no rush.", "It's normal to get stuck here, let's simplify."],
           "answer": ["Of course! Here's the answer, with a short why.", "Sure, here's the answer explained."]},
    "ar": {"question": ["سؤال رائع! لنستكشفه معًا.", "سؤال جيد، لننظر فيه معًا.", "لنمضِ خطوة بخطوة."],
           "correct": ["بالضبط! أنت تربط الأفكار جيدًا.", "أحسنت، فهمت الفكرة.", "صحيح! لنذهب أبعد قليلًا."],
           "incorrect": ["محاولة جيدة! بقيت نقطة صغيرة نوضحها.", "لا بأس، هكذا نتعلم.", "قريب! لننظر من زاوية أخرى."],
           "frustrated": ["لا تقلق، سنصل معًا.", "لا تستسلم، هذه الفكرة صعبة في البداية.", "خذ وقتك، لا داعي للعجلة."],
           "answer": ["بالتأكيد! إليك الإجابة مع شرح قصير.", "حسنًا، إليك الإجابة مشروحة."]},
}
_PRAISE_CORRECT = re.compile(r"(?i)\b(exact\w*|correct\w*|right|bravo|parfait\w*|excellent\w*|well done|"
                             r"bien jou\w*|c'est juste|juste !|perfect|great job|good job)\b|بالضبط|صحيح|أحسنت|ممتاز")
_FRUSTRATED = re.compile(r"(?i)(je (ne )?comprends (rien|pas)|j'y arrive pas|je n'y arrive pas|encore faux|nul|"
                         r"marre|abandonne|i don't understand|i give up|wrong again|i can't|لا أفهم|لم أفهم|صعب)")
_ASKS_ANSWER = re.compile(r"(?i)(donne[- ]moi la r[ée]ponse|dis[- ]moi (juste )?la r[ée]ponse|just (tell|give) me the "
                          r"answer|la solution directement|أعطني الإجابة)")


def situation(message: str, d: dict) -> str:
    """What the opener must fit: computed from the message (code) and the model's judgement of the answer."""
    if _ASKS_ANSWER.search(message):
        return "answer"
    if _FRUSTRATED.search(message) or d.get("student_mood") == "frustrated":
        return "frustrated"
    ans = str(d.get("student_answer", "none"))
    if ans == "correct":
        return "correct"
    if ans in ("incorrect", "partly_correct"):
        return "incorrect"
    return "question"


def choose_opener(raw: str, sit: str, lang: str, recent: list[str], env: str, amount: str) -> str:
    """Keep the model's opener when it fits; otherwise a fallback for the situation. Never praise a wrong answer as
    correct, never repeat a recent opener, keep it short (shorter for 'short' / 'small' preferences), calm = no '!'."""
    o = tidy(re.sub(r"\s+", " ", (raw or "").strip()))
    words = len(o.split())
    max_words = 10 if amount == "small" else 16
    low = {r.strip().lower() for r in recent}
    bad = (not o or words > max_words or o.lower() in low
           or (sit == "incorrect" and _PRAISE_CORRECT.search(o) and not re.search(r"(?i)presque|almost|tentative|attempt", o))
           or "\n" in o)
    if bad:
        bank = [x for x in OPENERS[lang][sit] if x.lower() not in low] or OPENERS[lang][sit]
        o = bank[len(recent) % len(bank)]
    if env == "calm":
        o = o.replace(" !", ".").replace("!", ".")
    return o


def _prefs_text(p: dict) -> str:
    v = {k: p.get(k) or DEFAULTS[k] for k in DEFAULTS}
    notes = p.get("notes") or {}
    extra = "\n".join(f"Student's own note ({k}): {str(t)[:200]}" for k, t in notes.items() if str(t).strip())
    return "\n".join([EXPLAIN[v["explanationStyle"]], AMOUNT[v["informationAmount"]], ENV[v["learningEnvironment"]],
                      TIMING[v["questionTiming"]]] + ([extra] if extra else []))


def _course(message: str, history: list[dict]) -> tuple[str, list[dict]]:
    """Passages matching the message (+ the previous student message), uploaded files first."""
    try:
        ix = rag.index()
    except Exception:  # noqa: BLE001
        return "(no course files)", []
    if not ix.chunks:
        return "(no course files uploaded)", []
    prev = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
    hits = [h for h in ix.search(f"{message} {prev}".strip(), 6) if h["relevant"]]
    hits.sort(key=lambda h: (h["folder"] != "uploads", -h["score"]))
    hits = hits[:3]
    if not hits:
        return "(nothing in the student's course files matches this question: use general knowledge and say so " \
               "briefly)", []
    body = "\n".join(f"[{h['file'].rsplit('/', 1)[-1]} p.{h['page']}] {h['text'][:1100]}" for h in hits)
    return ("Use these passages FIRST, with the course's terminology, and cite them as (file p.N). Say clearly when "
            "you add general knowledge that is not in the course. Never invent course content.\n" + body), hits


def _style_kwargs(p: dict, lang: str) -> dict:
    env = p.get("learningEnvironment") or DEFAULTS["learningEnvironment"]
    return {"max_words_per_sentence": 45, "neutral": env == "calm", "lang": lang,
            "max_questions": 1 if env == "calm" else 3}


def _check(text: str, suspects: dict, lang: str, kw: dict) -> list:
    return guards.check_studio({"a": text}, suspects, lang, style_kwargs=kw, purpose="tutor_chat_judge")["a"]


def _fallback(lang: str) -> str:
    return {"fr": "Je préfère vérifier avant de te répondre, et je n'y arrive pas pour l'instant. Peux-tu reformuler ta "
                  "question, ou me dire ce que tu as déjà compris ?",
            "ar": "أفضّل أن أتحقّق قبل أن أجيبك، ولم أتمكّن من ذلك الآن. هل يمكنك إعادة صياغة سؤالك، أو إخباري بما فهمته؟",
            "en": "I prefer to check before I answer, and I cannot do that right now. Could you rephrase your question, "
                  "or tell me what you already understood?"}[lang]


def turn(message: str, lang: str = "fr", session_id: str | None = None, student: dict | None = None,
         prefs: dict | None = None, want_media: str | None = None, doc_id: str | None = None) -> dict:
    """One tutor turn. `doc_id` = a PDF attached in the chat (engine/documents.py): its pages come first.
     `student` = students.from_token(...) result (profile read from the database) or None (guest:
    `prefs` from the request is used). `want_media` = 'image' | 'video' forces a media request (buttons)."""
    lang = lang_of(lang)
    message = (message or "").strip()[:2000]
    if not message:
        raise ValueError("empty message")
    sid = session_id if session_id and re.fullmatch(r"ts-[a-f0-9]{12}", session_id) else "ts-" + secrets.token_hex(6)
    profile = (student or {}).get("profile") or students.clean_profile(prefs or {})
    student_id = (student or {}).get("student_id")
    history = students.session_history(sid)
    recent = [h.get("opener", "") for h in history if h.get("role") == "assistant" and h.get("opener")][-5:]
    env = profile.get("learningEnvironment") or DEFAULTS["learningEnvironment"]
    opener = ""
    if doc_id:
        from engine import documents
        prev = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
        course, hits = documents.passages(doc_id, f"{message} {prev}")
    else:
        course, hits = _course(message, history)
    memory = students.memory_summary(student_id) if student_id else "(guest: nothing saved)"
    name = (profile.get("name") or "").strip().split(" ")[0]
    system = SYSTEM.format(name_part=f" called {name}" if name else "",
                           level_part=f" (level: {LEVELS.get(profile.get('educationLevel'), profile.get('educationLevel'))})"
                           if profile.get("educationLevel") else "",
                           lang=LANG[lang], prefs=_prefs_text(profile), memory=memory, course=course,
                           lang_name=LANG[lang].split(" (")[0], sugg=SUGG[lang],
                           recent_openers=" | ".join(recent) or "(none yet)")
    msgs = [{"role": "system", "content": system}]
    for h in history[-12:]:
        c = h["content"][:1500]
        # earlier tutor turns are replayed in the same JSON shape, so the model keeps answering in that shape
        msgs.append({"role": h["role"], "content": json.dumps({"reply": c}, ensure_ascii=False)
                     if h["role"] == "assistant" else c})
    # a picture / video asked for: TRACE draws it itself and shows it under the reply, so the tutor must not answer
    # "I cannot create videos" (it did, while the video was attached)
    asked = want_media or (("video" if _VIDEO_ASK.search(message) else "image") if _MEDIA_ASK.search(message) else None)
    media_note = ("\n\n(TRACE generates the " + ("narrated video" if asked == "video" else "diagram") + " itself and "
                  "shows it right under your reply. Never say you cannot create videos or images. Introduce it in one "
                  "short sentence, then explain the idea briefly.)") if asked else ""
    msgs.append({"role": "user", "content": message + media_note + "\n\n(Reply with the JSON object described above.)"})
    kw = _style_kwargs(profile, lang)
    suspects = {}
    d, text, checks = {}, "", []
    for attempt in range(2):
        try:
            # plain text mode + our own JSON parsing: Groq's JSON mode made gpt-oss emit tool calls (HTTP 400)
            r = llm.chat(llm.Request(messages=msgs, json_mode=False, purpose="tutor_chat", max_tokens=1600,
                                     temperature=0.3))
            d = _json(r.text)
        except Exception:  # noqa: BLE001  offline and not cached / all models unavailable
            d = {}
            break
        body = tidy(str(d.get("reply", "")))
        if not body:
            continue
        sit = situation(message, d)
        opener = "" if str(d.get("mode")) == "refusal" else choose_opener(
            str(d.get("opener", "")), sit, lang, recent, env, profile.get("informationAmount") or "normal")
        if opener and body.lower().startswith(opener.lower()[:20]):
            body = body[len(opener):].lstrip(" \n")  # the model repeated its opener at the start of the reply
        text = f"{opener}\n\n{body}" if opener else body
        checks = _check(text, suspects, lang, kw)
        failed = [c for c in checks if c.status == "fail"]
        if not failed:
            break
        msgs = msgs + [{"role": "assistant", "content": text},
                       {"role": "user", "content": "(System check, not the student: rewrite your last reply so it "
                        "passes these checks, keep the same teaching intent: " + "; ".join(f"{c.name}: {c.detail}"
                                                                                           for c in failed)[:600] + ")"}]
        text = ""
    ok = bool(text) and checks and not any(c.status == "fail" for c in checks)
    if ok:
        reply = safetext.from_guards(text, checks, lang=lang)
    else:
        reply = safetext.static(_fallback(lang), lang=lang, style_kwargs={"max_words_per_sentence": 40,
                                                                           "max_questions": 2})
    mode = str(d.get("mode", "")) if ok else "fallback"
    suggestions = [str(s)[:40] for s in (d.get("suggestions") or []) if str(s).strip()][:3] if ok else []
    # media: asked by the student (buttons or words) or proposed by the tutor
    media_req = d.get("media") if ok and isinstance(d.get("media"), dict) else None
    kind = want_media or (("video" if _VIDEO_ASK.search(message) else "image") if _MEDIA_ASK.search(message) else None)
    if kind and mode != "refusal":
        req_text = (media_req or {}).get("request")
        if not req_text:
            # a button press: draw the lesson being discussed, not only the last line (often an answer like "Δ = 1")
            topic = next((h["content"] for h in history if h["role"] == "user"), message)
            last_tutor = next((h["content"] for h in reversed(history) if h["role"] == "assistant" and h["content"]), "")
            req_text = (f"Lesson topic: {topic[:300]}. Latest student message: {message[:300]}. "
                        f"Latest tutor explanation: {last_tutor[:500]}. Show what helps understand this lesson.")
        media_req = {"type": kind, "request": req_text}
    if media_req and media_req.get("type") == "video" and not (want_media == "video" or _VIDEO_ASK.search(message)):
        media_req = {**media_req, "type": "image"}  # videos only on the student's request
    media_out = None
    if media_req and media_req.get("type") in ("image", "video") and mode != "refusal":
        media_out = make_media(media_req["type"], str(media_req.get("request") or message), lang, profile, hits)
    # memory + history
    # a first question shows nothing about understanding: observations only once the student answers the tutor
    obs = [o for o in (d.get("observations") or []) if isinstance(o, dict)][:4] if ok and history else []
    if student_id and obs:
        students.observe(student_id, obs, helped_by=profile.get("explanationStyle"))
    history = history + [{"role": "user", "content": message},
                         {"role": "assistant", "content": reply.text if reply.shown_allowed else "",
                          "opener": opener if ok else ""}]
    students.save_history(sid, student_id, history)
    progress = sum(1 for o in obs if o.get("status") == "understood")
    return TutorChatTurn(session_id=sid, reply=reply, mode=mode, suggestions=suggestions, media=media_out,
                         citations=[{"file": h["file"], "page": h["page"]} for h in hits] if ok and d.get("uses_course")
                         else [], observations=[{"concept": str(o.get("concept", ""))[:80],
                                                 "status": str(o.get("status", ""))} for o in obs],
                         understood_now=progress, preferences_used={k: profile.get(k) or DEFAULTS[k]
                                                                    for k in DEFAULTS}).model_dump()


def make_media(kind: str, request: str, lang: str, profile: dict | None = None, hits: list[dict] | None = None) -> dict:
    from engine import media
    ctx = "\n".join(h["text"][:800] for h in (hits or []))
    calm = (profile or {}).get("learningEnvironment") == "calm"
    try:
        m = media.image(request, lang, ctx) if kind == "image" else media.video(request, lang, ctx, calm=calm)
        return ChatMedia(**{k: m.get(k) for k in ("type", "url", "title", "caption", "subtitles_url", "duration_s")},
                         ok=True).model_dump()
    except media.MediaError as e:
        from engine.i18n import t as tr
        return ChatMedia(type=kind, ok=False, error=tr(e.key, lang)).model_dump()
    except Exception:  # noqa: BLE001  unexpected failure (ffmpeg, voice, disk): the tutor reply is still returned
        import traceback
        from engine.i18n import t as tr
        try:
            log = media.OUT / "errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(f"--- {kind}: {request[:120]!r}\n{traceback.format_exc()}\n")
        except OSError:
            pass
        return ChatMedia(type=kind, ok=False, error=tr("media_unavailable", lang)).model_dump()
