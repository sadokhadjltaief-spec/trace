"""Educational images and short videos on request (student or tutor).

Images are never AI-generated pixels (CLAUDE.md section 12: generated images can draw wrong maths). The LLM only
picks ONE diagram type from a whitelist and its parameters (pydantic-validated); the picture is drawn by matplotlib and
every number in it is computed (function values with SymPy, triangle hypotenuse, fraction bars, bar heights).
Every text in the picture passes the math check (SymPy) before drawing.

Videos: the LLM writes a short script (3-6 scenes: title, up to 3 bullets, narration, optional diagram spec); the
texts pass the guards; each scene is rendered as a 1280x720 slide (+ its computed diagram), narrated with edge-tts
(online neural voices) or the Windows voices through pyttsx3 (offline), and assembled with the ffmpeg binary of
imageio-ffmpeg. Subtitles are WebVTT. Outputs are cached by content hash in exports/media/ and served by GET /api/v1/media/{name}.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
import textwrap
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from engine import ROOT, guards, llm
from engine.i18n import lang_of

OUT = ROOT / "exports" / "media"
FONTS = ROOT / "assets" / "fonts"
NAME = re.compile(r"^[a-f0-9]{16}\.(png|mp4|vtt)$")
COLORS = ["#f08a24", "#3a9ad9", "#7c4dff", "#20b2aa", "#e0457b", "#8bc34a"]
LANG = {"fr": "French", "ar": "Modern Standard Arabic", "en": "English"}
VOICES = {"fr": "fr-FR-DeniseNeural", "ar": "ar-TN-ReemNeural", "en": "en-US-JennyNeural"}


class MediaError(Exception):
    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key


# ---------------------------------------------------------------- diagram specs (whitelist)
class Point(BaseModel):
    value: float
    label: str = ""


class Event(BaseModel):
    when: str = Field(max_length=20)
    text: str = Field(max_length=80)


class Spec(BaseModel):
    kind: Literal["function_plot", "number_line", "fraction_bars", "bar_chart", "right_triangle", "table", "steps",
                  "timeline", "shape"]
    title: str = Field("", max_length=90)
    caption: str = Field("", max_length=240)
    expressions: list[str] = Field(default_factory=list, max_length=3)   # function_plot, in x
    x_min: float = -5
    x_max: float = 5
    points: list[Point] = Field(default_factory=list, max_length=10)     # number_line
    fractions: list[str] = Field(default_factory=list, max_length=5)     # fraction_bars, "a/b"
    labels: list[str] = Field(default_factory=list, max_length=10)       # bar_chart
    values: list[float] = Field(default_factory=list, max_length=10)     # bar_chart
    y_label: str = Field("", max_length=40)
    a: float = 3                                                         # right_triangle legs
    b: float = 4
    headers: list[str] = Field(default_factory=list, max_length=6)       # table
    rows: list[list[str]] = Field(default_factory=list, max_length=8)
    steps: list[str] = Field(default_factory=list, max_length=6)         # steps
    events: list[Event] = Field(default_factory=list, max_length=8)      # timeline
    shape: Literal["circle", "rectangle", "square"] = "circle"           # shape
    width: float = 4
    height: float = 3

    @field_validator("x_max")
    @classmethod
    def _range(cls, v, info):
        lo = info.data.get("x_min", -5)
        if not (-1e4 < lo < v < 1e4):
            raise ValueError("bad x range")
        return v

    @field_validator("a", "b", "width", "height")
    @classmethod
    def _pos(cls, v):
        if not 0 < v <= 1000:
            raise ValueError("must be positive")
        return v


SPEC_DOC = """Diagram kinds (choose the ONE that best helps):
- function_plot: expressions (1-3, in x, Python/SymPy syntax like "x**2-4*x+3"), x_min, x_max
- number_line: points [{value, label}]
- fraction_bars: fractions ["1/3", "2/5"] (positive, denominators up to 24)
- bar_chart: labels, values, y_label (only real, given numbers; never invent statistics)
- right_triangle: a, b (the two legs; the hypotenuse is computed)
- table: headers, rows (short cells)
- steps: steps (2-6 short labelled steps of a method or process)
- timeline: events [{when, text}] (history, sequences)
- shape: shape circle|rectangle|square, width, height (circle: width = radius); area/perimeter are computed
Always: title, caption (one sentence that explains what to look at)."""

IMAGE_SYS = """You design ONE clear educational diagram for a school student, written in {lang}.
{doc}
Use only facts you are sure of. Do not draw anything unsafe or unrelated to learning; if the request is not about
learning, return {{"kind": "none"}}.
Return JSON with the fields of the chosen kind, e.g. {{"kind": "function_plot", "title": "...", "caption": "...",
"expressions": ["x**2-4"], "x_min": -4, "x_max": 4}}"""

VIDEO_SYS = """You write the script of a short educational video (60 to 90 seconds) for a school student, in {lang}.
3 to 5 scenes. Each scene: "title" (max 8 words), "bullets" (1-3 short lines, maths as plain text), "narration" (what
the voice says, max 40 words, plain sentences, no symbols that cannot be read aloud), and optionally "diagram" (one
diagram spec from the list below) when a picture really helps.
{doc}
Start with an example or a question, end with a one-line recap. Every equality must be true. Use only facts you are
sure of. {style}
If the request is not about learning, return {{"scenes": []}}.
Return JSON: {{"title": "...", "scenes": [{{"title": "...", "bullets": ["..."], "narration": "...", "diagram": {{...}}}}]}}"""


# ---------------------------------------------------------------- drawing
def _ar(text: str) -> str:
    if not re.search(r"[؀-ۿ]", text or ""):
        return text
    import arabic_reshaper
    from bidi.algorithm import get_display
    return get_display(arabic_reshaper.reshape(text))


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ("NotoSans.ttf", "NotoNaskhArabic.ttf"):
        if (FONTS / f).exists():
            font_manager.fontManager.addfont(str(FONTS / f))
    plt.rcParams.update({"font.family": ["Noto Sans", "Noto Naskh Arabic", "DejaVu Sans"], "font.size": 13,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#9aa4b2",
                         "axes.titleweight": "bold", "axes.titlesize": 17})
    return plt


def _texts(spec: Spec) -> list[str]:
    t = [spec.title, spec.caption, *spec.labels, *spec.steps, *[c for r in spec.rows for c in r], *spec.headers,
         *[e.text for e in spec.events], *[p.label for p in spec.points]]
    return [x for x in t if x and x.strip()]


def check_spec(spec: Spec) -> list[str]:
    """Deterministic checks before drawing: SymPy-parseable expressions, valid fractions, true equalities in texts."""
    import sympy as sp
    bad = []
    x = sp.Symbol("x")
    for e in spec.expressions:
        try:
            expr = sp.sympify(e.replace("^", "**"), locals={"x": x})
            if expr.free_symbols - {x}:
                bad.append(f"expression has other variables: {e}")
        except Exception:  # noqa: BLE001
            bad.append(f"cannot read expression: {e}")
    for f in spec.fractions:
        try:
            fr = Fraction(f.replace(" ", ""))
            if not (0 < fr <= 4 and fr.denominator <= 24):
                bad.append(f"fraction out of range: {f}")
        except (ValueError, ZeroDivisionError):
            bad.append(f"not a fraction: {f}")
    if spec.kind == "bar_chart" and (not spec.values or len(spec.values) != len(spec.labels)):
        bad.append("bar chart needs one value per label")
    if spec.kind == "function_plot" and not spec.expressions:
        bad.append("no expression")
    for t in _texts(spec):
        status, detail = guards.math_check(t)
        if status == "fail":
            bad.append(detail)
    return bad


def _draw_on(ax, spec: Spec, lang: str) -> None:
    import numpy as np
    import sympy as sp
    k = spec.kind
    if k == "function_plot":
        x = sp.Symbol("x")
        xs = np.linspace(spec.x_min, spec.x_max, 400)
        sup = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
        for i, e in enumerate(spec.expressions):
            expr = sp.sympify(e.replace("^", "**"), locals={"x": x})
            f = sp.lambdify(x, expr, "numpy")
            ys = np.broadcast_to(np.asarray(f(xs), dtype=float), xs.shape)
            shown = re.sub(r"\*\*(\d+)", lambda m: m.group(1).translate(sup), str(expr)).replace("*", "")
            color = COLORS[i % len(COLORS)]
            ax.plot(xs, ys, lw=3, color=color, label=f"y = {shown}")
            # computed key points: real roots in range, and the vertex of a quadratic
            try:
                if expr.is_polynomial(x) and sp.degree(expr, x) <= 4:
                    for r in sp.real_roots(sp.Poly(expr, x)):
                        rv = float(r)
                        if spec.x_min <= rv <= spec.x_max:
                            ax.plot(rv, 0, "o", ms=10, color=color, mec="white", mew=2, zorder=5)
                            ax.annotate(f"x = {sp.nsimplify(r) if r.is_rational else round(rv, 3)}", (rv, 0),
                                        textcoords="offset points", xytext=(0, 12), ha="center", fontsize=12,
                                        fontweight="bold", color=color)
                    if sp.degree(expr, x) == 2:
                        a2, b2 = sp.Poly(expr, x).all_coeffs()[:2]
                        xv = -b2 / (2 * a2)
                        yv = expr.subs(x, xv)
                        if spec.x_min <= float(xv) <= spec.x_max:
                            ax.plot(float(xv), float(yv), "s", ms=9, color="#7c4dff", zorder=5)
                            ax.annotate(f"({sp.nsimplify(xv)} ; {sp.nsimplify(yv)})", (float(xv), float(yv)),
                                        textcoords="offset points", xytext=(0, -20), ha="center", fontsize=12,
                                        color="#7c4dff")
            except Exception:  # noqa: BLE001  key points are a bonus; the curve itself is always drawn
                pass
        ax.axhline(0, color="#9aa4b2", lw=1)
        ax.axvline(0, color="#9aa4b2", lw=1)
        ax.grid(alpha=0.25)
        ax.legend(frameon=False)
    elif k == "number_line":
        vals = [p.value for p in spec.points] or [0]
        lo, hi = min(vals + [0]) - 1, max(vals + [0]) + 1
        ax.axhline(0, color="#334155", lw=2)
        for t in np.arange(np.floor(lo), np.ceil(hi) + 1):
            ax.plot([t, t], [-0.08, 0.08], color="#334155", lw=1.5)
            ax.text(t, -0.25, f"{t:g}", ha="center", va="top", fontsize=12)
        for i, p in enumerate(spec.points):
            ax.plot(p.value, 0, "o", ms=14, color=COLORS[i % len(COLORS)])
            ax.text(p.value, 0.25, _ar(p.label or f"{p.value:g}"), ha="center", va="bottom", fontsize=13, fontweight="bold")
        ax.set_ylim(-1, 1)
        ax.set_xlim(lo - 0.3, hi + 0.3)
        ax.axis("off")
    elif k == "fraction_bars":
        frs = [Fraction(f.replace(" ", "")) for f in spec.fractions]
        for row, fr in enumerate(frs):
            y = len(frs) - row
            whole = max(1, int(np.ceil(float(fr))))
            for w in range(whole):
                for j in range(fr.denominator):
                    filled = (w * fr.denominator + j) < fr.numerator
                    ax.add_patch(__import__("matplotlib").patches.Rectangle(
                        (w + j / fr.denominator, y), 1 / fr.denominator, 0.6,
                        facecolor=COLORS[row % len(COLORS)] if filled else "#eef2f7", edgecolor="#334155", lw=1.5))
            ax.text(-0.15, y + 0.3, f"{fr.numerator}/{fr.denominator}", ha="right", va="center", fontsize=16,
                    fontweight="bold")
        ax.set_xlim(-0.35, max(1, max(np.ceil(float(f)) for f in frs)) + 0.05)
        ax.set_ylim(0.6, len(frs) + 0.9)
        ax.axis("off")
    elif k == "bar_chart":
        ax.bar([_ar(s) for s in spec.labels], spec.values, color=[COLORS[i % len(COLORS)] for i in range(len(spec.values))])
        for i, v in enumerate(spec.values):
            ax.text(i, v, f"{v:g}", ha="center", va="bottom", fontweight="bold")
        ax.set_ylabel(_ar(spec.y_label))
        ax.grid(axis="y", alpha=0.25)
    elif k == "right_triangle":
        a, b = spec.a, spec.b
        c = (a * a + b * b) ** 0.5
        ax.add_patch(__import__("matplotlib").patches.Polygon([[0, 0], [b, 0], [0, a]], closed=True,
                                                               facecolor="#fde7d1", edgecolor="#f08a24", lw=3))
        s = min(a, b) * 0.12
        ax.add_patch(__import__("matplotlib").patches.Rectangle((0, 0), s, s, fill=False, edgecolor="#334155", lw=1.5))
        ax.text(b / 2, -0.08 * a, f"b = {b:g}", ha="center", va="top", fontsize=15, fontweight="bold")
        ax.text(-0.06 * b, a / 2, f"a = {a:g}", ha="right", va="center", fontsize=15, fontweight="bold")
        ax.text(b / 2 + 0.05 * b, a / 2 + 0.05 * a, f"c = √({a:g}² + {b:g}²) = {c:.4g}", ha="left", va="bottom",
                fontsize=15, fontweight="bold", color="#7c4dff")
        ax.set_aspect("equal")
        ax.set_xlim(-0.35 * b, 1.6 * b)
        ax.set_ylim(-0.25 * a, 1.15 * a)
        ax.axis("off")
    elif k == "table":
        cells = [[_ar(c)[:28] for c in r] for r in spec.rows] or [[""]]
        n = max(len(r) for r in cells + [spec.headers or [""]])
        cells = [r + [""] * (n - len(r)) for r in cells]
        hdr = ([_ar(h)[:28] for h in spec.headers] + [""] * n)[:n] if spec.headers else None
        tb = ax.table(cellText=cells, colLabels=hdr, loc="center", cellLoc="center")
        tb.auto_set_font_size(False)
        tb.set_fontsize(13)
        tb.scale(1, 2.2)
        for (r, _), cell in tb.get_celld().items():
            cell.set_edgecolor("#cbd5e1")
            if r == 0 and hdr:
                cell.set_facecolor("#f08a24")
                cell.set_text_props(color="white", fontweight="bold")
        ax.axis("off")
    elif k == "steps":
        n = len(spec.steps)
        for i, s in enumerate(spec.steps):
            y = n - i
            ax.add_patch(__import__("matplotlib").patches.FancyBboxPatch((0.05, y - 0.3), 0.9, 0.6,
                         boxstyle="round,pad=0.02,rounding_size=0.08", facecolor="#fff4e8" if i % 2 == 0 else "#e8f3fb",
                         edgecolor=COLORS[i % 2], lw=2))
            ax.text(0.1, y, f"{i + 1}", fontsize=22, fontweight="bold", color=COLORS[i % 2], va="center")
            ax.text(0.17, y, "\n".join(textwrap.wrap(_ar(s), 55)), fontsize=16, va="center")
            if i < n - 1:
                ax.annotate("", xy=(0.5, y - 0.68), xytext=(0.5, y - 0.32),
                            arrowprops=dict(arrowstyle="-|>", color="#9aa4b2", lw=2))
        ax.set_xlim(0, 1)
        ax.set_ylim(0.4, n + 0.5)
        ax.axis("off")
    elif k == "timeline":
        n = len(spec.events)
        ax.axhline(0, color="#334155", lw=3)
        for i, e in enumerate(spec.events):
            ax.plot(i, 0, "o", ms=16, color=COLORS[i % len(COLORS)])
            up = 1 if i % 2 == 0 else -1
            ax.text(i, 0.25 * up, _ar(e.when), ha="center", va="bottom" if up > 0 else "top", fontsize=14, fontweight="bold")
            ax.text(i, 0.55 * up, "\n".join(textwrap.wrap(_ar(e.text), 22)), ha="center",
                    va="bottom" if up > 0 else "top", fontsize=11)
        ax.set_xlim(-0.7, max(n, 1) - 0.3)
        ax.set_ylim(-1.6, 1.6)
        ax.axis("off")
    elif k == "shape":
        import matplotlib.patches as mp
        w, h = spec.width, (spec.width if spec.shape == "square" else spec.height)
        if spec.shape == "circle":
            ax.add_patch(mp.Circle((0, 0), w, facecolor="#e8f3fb", edgecolor="#3a9ad9", lw=3))
            ax.plot([0, w], [0, 0], color="#f08a24", lw=3)
            ax.text(w / 2, 0.05 * w, f"r = {w:g}", ha="center", va="bottom", fontsize=15, fontweight="bold")
            ax.text(0, -1.3 * w, f"A = π × {w:g}² ≈ {3.141592653589793 * w * w:.4g}    P = 2 × π × {w:g} ≈ "
                                 f"{2 * 3.141592653589793 * w:.4g}", ha="center", fontsize=14, color="#7c4dff")
            ax.set_xlim(-1.5 * w, 1.5 * w)
            ax.set_ylim(-1.5 * w, 1.2 * w)
        else:
            ax.add_patch(mp.Rectangle((0, 0), w, h, facecolor="#fff4e8", edgecolor="#f08a24", lw=3))
            ax.text(w / 2, -0.08 * h, f"{w:g}", ha="center", va="top", fontsize=15, fontweight="bold")
            ax.text(-0.05 * w, h / 2, f"{h:g}", ha="right", va="center", fontsize=15, fontweight="bold")
            ax.text(w / 2, h / 2, f"A = {w:g} × {h:g} = {w * h:g}\nP = 2 × ({w:g} + {h:g}) = {2 * (w + h):g}",
                    ha="center", va="center", fontsize=14, color="#7c4dff")
            ax.set_xlim(-0.4 * w, 1.3 * w)
            ax.set_ylim(-0.4 * h, 1.2 * h)
        ax.set_aspect("equal")
        ax.axis("off")


def render(spec: Spec, path: Path, lang: str = "fr", size=(10, 6.2)) -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=size, dpi=110)
    fig.patch.set_facecolor("white")
    _draw_on(ax, spec, lang)
    if spec.title:
        ax.set_title(_ar(spec.title), pad=14)
    if spec.caption:
        fig.text(0.5, 0.02, "\n".join(textwrap.wrap(_ar(spec.caption), 110)), ha="center", va="bottom", fontsize=11,
                 color="#475569")
    fig.tight_layout(rect=(0, 0.07 if spec.caption else 0, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    return path


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _spec_from(d: dict) -> Spec | None:
    if not isinstance(d, dict) or d.get("kind") in (None, "none"):
        return None
    try:
        spec = Spec.model_validate(d)
    except ValidationError:
        return None
    return None if check_spec(spec) else spec


def image(request: str, lang: str = "fr", context: str = "") -> dict:
    """Diagram for the request: {kind, url, title, caption}. Raises MediaError."""
    lang = lang_of(lang)
    request = (request or "").strip()[:500]
    if not request:
        raise MediaError("media_empty")
    user = f"Student request: {request}" + (f"\n\nCourse context (use its notation):\n{context[:2500]}" if context else "")
    spec = None
    for attempt in range(2):
        try:
            d = llm.ask_json(IMAGE_SYS.format(lang=LANG[lang], doc=SPEC_DOC), user + ("\n(retry: previous spec was "
                             "invalid, choose a simpler kind)" if attempt else ""), purpose="media_image",
                             max_tokens=1500) or {}
        except Exception as e:  # noqa: BLE001
            raise MediaError("media_unavailable", str(e)[:120]) from e
        if d.get("kind") in ("none", None):
            raise MediaError("media_off_topic")
        spec = _spec_from(d)
        if spec:
            break
    if not spec:
        raise MediaError("media_invalid")
    name = _key("img", spec.model_dump(), lang) + ".png"
    path = OUT / name
    if not path.exists():
        render(spec, path, lang)
    return {"type": "image", "kind": spec.kind, "url": f"/engine/media/{name}", "title": spec.title,
            "caption": spec.caption}


# ---------------------------------------------------------------- video
def _slide(scene: dict, idx: int, total: int, title: str, path: Path, lang: str) -> Path:
    plt = _plt()
    fig = plt.figure(figsize=(12.8, 7.2), dpi=100)
    fig.patch.set_facecolor("#0f1b2d")
    fig.text(0.04, 0.92, _ar(title)[:70], color="#f5a03f", fontsize=15, fontweight="bold")
    fig.text(0.96, 0.92, f"{idx}/{total}", color="#94a3b8", fontsize=14, ha="right")
    fig.text(0.04, 0.82, _ar(scene["title"]), color="white", fontsize=28, fontweight="bold")
    spec = scene.get("spec")
    left_w = 0.44 if spec else 0.9
    y = 0.68
    for b in scene.get("bullets", [])[:3]:
        lines = textwrap.wrap(_ar(b), 34 if spec else 70)
        fig.text(0.05, y, "•", color="#f5a03f", fontsize=24, va="top")
        fig.text(0.08, y, "\n".join(lines), color="#e2e8f0", fontsize=19, va="top", linespacing=1.4)
        y -= 0.075 * len(lines) + 0.06
    if spec:
        ax = fig.add_axes((0.5, 0.17, 0.46, 0.6))
        ax.set_facecolor("white")
        _draw_on(ax, spec, lang)
        ax.patch.set_alpha(1)
        fig.patches.append(__import__("matplotlib").patches.FancyBboxPatch((0.49, 0.15), 0.48, 0.64,
                           boxstyle="round,pad=0.005,rounding_size=0.02", transform=fig.transFigure,
                           facecolor="white", edgecolor="none", zorder=-1))
    sub = "\n".join(textwrap.wrap(_ar(scene["narration"]), 95)[:2])
    fig.text(0.5, 0.05, sub, color="white", fontsize=14, ha="center", va="bottom",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#000000", alpha=0.55, edgecolor="none"))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def _tts(text: str, lang: str, out_base: Path) -> Path:
    """edge-tts (online) -> mp3; else pyttsx3 (Windows voices, offline) -> wav."""
    if not llm.demo_mode():
        try:
            import edge_tts
            mp3 = out_base.with_suffix(".mp3")

            async def go():
                await edge_tts.Communicate(text, VOICES[lang], rate="-5%").save(str(mp3))
            asyncio.run(go())
            if mp3.exists() and mp3.stat().st_size > 1000:
                return mp3
        except Exception:  # noqa: BLE001  no internet: offline voice
            pass
    import pyttsx3
    wav = out_base.with_suffix(".wav")
    eng = pyttsx3.init()
    want = {"fr": "french", "en": "english", "ar": "arab"}[lang]
    for v in eng.getProperty("voices"):
        if want in (v.name or "").lower():
            eng.setProperty("voice", v.id)
            break
    eng.setProperty("rate", 165)
    eng.save_to_file(text, str(wav))
    eng.runAndWait()
    if not wav.exists():
        raise MediaError("media_voice", "no voice")
    return wav


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run ffmpeg with its own empty stdin and no console window. Inheriting the server's stdin failed when the engine
    had been started from a shell that has since exited (the inherited handle is no longer valid on Windows)."""
    return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _duration(audio: Path) -> float:
    r = _run([_ffmpeg(), "-i", str(audio)])
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 5.0


def _vtt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def video(request: str, lang: str = "fr", context: str = "", calm: bool = False) -> dict:
    """Short narrated explainer video: {url, subtitles_url, title, scenes:[{title}], duration_s}."""
    lang = lang_of(lang)
    request = (request or "").strip()[:500]
    if not request:
        raise MediaError("media_empty")
    style = "Calm, neutral tone, no exclamation marks." if calm else "Friendly, encouraging tone."
    user = f"Student request: {request}" + (f"\n\nCourse context (use its notation):\n{context[:3000]}" if context else "")
    try:
        d = llm.ask_json(VIDEO_SYS.format(lang=LANG[lang], doc=SPEC_DOC, style=style), user, purpose="media_video",
                         max_tokens=3500) or {}
    except Exception as e:  # noqa: BLE001
        raise MediaError("media_unavailable", str(e)[:120]) from e
    raw = [s for s in (d.get("scenes") or []) if isinstance(s, dict) and s.get("narration")][:5]
    if not raw:
        raise MediaError("media_off_topic")
    texts = {}
    for i, s in enumerate(raw):
        texts[f"s{i}"] = " ".join([str(s.get("title", "")), *map(str, (s.get("bullets") or [])[:3]),
                                   str(s.get("narration", ""))])
    checks = guards.check_studio(texts, {}, lang, style_kwargs={"max_words_per_sentence": 45, "max_questions": 3,
                                                               "neutral": calm, "lang": lang},
                                 purpose="media_video_judge")
    scenes = []
    for i, s in enumerate(raw):
        if any(c.status == "fail" and c.name in ("math", "congruency", "style") for c in checks[f"s{i}"]):
            continue  # a scene with a false equality or a style problem is dropped, never shown
        scenes.append({"title": str(s.get("title", ""))[:60], "bullets": [str(b)[:120] for b in (s.get("bullets") or [])[:3]],
                       "narration": str(s.get("narration", ""))[:400], "spec": _spec_from(s.get("diagram") or {})})
    if len(scenes) < 2:
        raise MediaError("media_invalid")
    title = str(d.get("title") or request)[:80]
    key = _key("vid", title, [{**s, "spec": s["spec"].model_dump() if s["spec"] else None} for s in scenes], lang)
    mp4, vtt = OUT / f"{key}.mp4", OUT / f"{key}.vtt"
    if not mp4.exists():
        work = OUT / f"work-{key}"
        work.mkdir(parents=True, exist_ok=True)
        parts, t0, cues = [], 0.0, []
        for i, s in enumerate(scenes, 1):
            png = _slide(s, i, len(scenes), title, work / f"s{i}.png", lang)
            audio = _tts(s["narration"], lang, work / f"s{i}")
            dur = _duration(audio) + 0.6
            part = work / f"s{i}.mp4"
            r = _run([_ffmpeg(), "-y", "-loop", "1", "-i", str(png), "-i", str(audio), "-c:v", "libx264",
                      "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "25", "-c:a", "aac", "-b:a", "128k",
                      "-ar", "44100", "-ac", "1", "-t", f"{dur:.2f}", "-af", "apad", str(part)])
            if r.returncode != 0:
                raise MediaError("media_render", r.stderr[-300:])
            parts.append(part)
            cues.append(f"{i}\n{_vtt_time(t0)} --> {_vtt_time(t0 + dur - 0.3)}\n{s['narration']}\n")
            t0 += dur
        lst = work / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        r = _run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(mp4)])
        if r.returncode != 0 or not mp4.exists():
            raise MediaError("media_render", r.stderr[-300:])
        vtt.write_text("WEBVTT\n\n" + "\n".join(cues), encoding="utf-8")
    dur = _duration(mp4)
    return {"type": "video", "url": f"/engine/media/{mp4.name}", "subtitles_url": f"/engine/media/{vtt.name}",
            "title": title, "scenes": [s["title"] for s in scenes], "duration_s": round(dur, 1),
            "caption": title}


def path_of(name: str) -> Path:
    if not NAME.match(name or ""):
        raise KeyError(name)
    p = OUT / name
    if not p.exists():
        raise FileNotFoundError(name)
    return p
