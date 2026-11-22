"""Text from a YouTube video (its transcript) or a Wikipedia article, cut into numbered "pages" (parts) so the
practice tools (summary, flashcards, quiz) use them like a file: every generated line cites its part.

- YouTube: youtube-transcript-api (captions written by the channel first, then automatic ones; fr, ar, en, then any).
  Videos without captions are refused with a clear message (no audio transcription here).
- Wikipedia: the public MediaWiki API (plain-text extract), one part per section; reference sections dropped.
  Wikipedia text is CC BY-SA: the article link is kept as the source.
- Every fetched text is cached in .cache/web/ (by URL). In demo mode (TRACE_DEMO=1) only the cache is read, so a source
  fetched once before the video works offline; anything else gets the "needs internet" message.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from engine import ROOT, llm

CACHE = ROOT / ".cache" / "web"
UA = "TRACE-edu/1.0 (educational study app)"
PART_CHARS = 1500
MAX_PARTS = 14
_SKIP_SECTIONS = re.compile(r"(?i)^(notes?( et références)?|références|bibliographie|voir aussi|liens externes|articles connexes|"
                            r"references|see also|external links|further reading|bibliography|المراجع|وصلات خارجية|انظر أيضا)$")


class SourceError(Exception):
    """Extraction failed; `key` is an i18n key for the student-facing message."""

    def __init__(self, key: str, detail: str = ""):
        super().__init__(detail or key)
        self.key = key


# ---------------------------------------------------------------- parsing links
def youtube_id(link: str) -> str | None:
    s = (link or "").strip()
    if re.fullmatch(r"[\w-]{11}", s):
        return s
    try:
        u = urlparse(s if "://" in s else "https://" + s)
    except ValueError:
        return None
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        if u.path == "/watch":
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"^/(?:shorts|embed|live|v)/([\w-]{11})", u.path)
            vid = m.group(1) if m else ""
    else:
        return None
    return vid if re.fullmatch(r"[\w-]{11}", vid or "") else None


def wikipedia_page(link: str, default_lang: str = "fr") -> tuple[str, str] | None:
    """('fr', 'Théorème de Pythagore') from a Wikipedia link, or from a plain title (in the student's language)."""
    s = (link or "").strip()
    if not s:
        return None
    if "wikipedia.org" in s:
        u = urlparse(s if "://" in s else "https://" + s)
        lang = (u.hostname or "").split(".")[0].removeprefix("www") or default_lang
        if lang in ("m", ""):
            lang = default_lang
        m = re.match(r"^/wiki/(.+)$", u.path)
        title = unquote(m.group(1)).replace("_", " ") if m else (parse_qs(u.query).get("title") or [""])[0]
        return (lang, title.split("#")[0]) if title else None
    if "://" in s or "/" in s or len(s) > 120:
        return None
    return default_lang, s


# ---------------------------------------------------------------- cache
def _cache_file(key: str) -> Path:
    return CACHE / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:24] + ".json")


def _cached(key: str) -> dict | None:
    f = _cache_file(key)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _store(key: str, d: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    _cache_file(key).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _parts(blocks: list[str], name: str) -> list[tuple[str, int, str]]:
    """Group text blocks into parts of ~PART_CHARS characters (file name, part number, text)."""
    out, cur = [], ""
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if cur and len(cur) + len(b) > PART_CHARS:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + b).strip()
    if cur:
        out.append(cur)
    return [(name, i, t) for i, t in enumerate(out[:MAX_PARTS], 1)]


def _mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


# ---------------------------------------------------------------- fetchers
def _fetch_youtube(vid: str, langs: list[str]) -> dict:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api import _errors as E
    except ImportError as e:  # pragma: no cover
        raise SourceError("source_unavailable", "youtube-transcript-api is not installed") from e
    api = YouTubeTranscriptApi()
    try:
        listing = api.list(vid)
        tr = None
        for finder in (listing.find_manually_created_transcript, listing.find_generated_transcript):
            try:
                tr = finder(langs)
                break
            except E.NoTranscriptFound:
                continue
        if tr is None:
            tr = next(iter(listing))  # any language the video has
        snippets = tr.fetch()
        lang = tr.language_code
    except (E.TranscriptsDisabled, E.NoTranscriptFound, StopIteration) as e:
        raise SourceError("source_youtube_no_transcript", type(e).__name__) from e
    except (E.VideoUnavailable, E.InvalidVideoId) as e:
        raise SourceError("source_youtube_unavailable", type(e).__name__) from e
    except E.CouldNotRetrieveTranscript as e:  # blocked IP, age restriction, network error inside the library
        raise SourceError("source_offline" if "connect" in str(e).lower() else "source_youtube_unavailable",
                          type(e).__name__) from e
    except OSError as e:
        raise SourceError("source_offline", type(e).__name__) from e
    # one line per ~30 s, with its time stamp, so the summary can be checked against the video
    blocks, cur, t0 = [], [], None
    for sn in snippets:
        text = re.sub(r"\s+", " ", str(sn.text).replace("\n", " ")).strip()
        if not text or re.fullmatch(r"\[[^\]]*\]|♪+", text):
            continue
        if t0 is None:
            t0 = sn.start
        cur.append(text)
        if sn.start - t0 >= 30:
            blocks.append(f"[{_mmss(t0)}] " + " ".join(cur))
            cur, t0 = [], None
    if cur:
        blocks.append(f"[{_mmss(t0 or 0)}] " + " ".join(cur))
    if not blocks:
        raise SourceError("source_youtube_no_transcript", "empty transcript")
    return {"kind": "youtube", "id": vid, "lang": lang, "title": vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "blocks": blocks}


def _fetch_wikipedia(lang: str, title: str) -> dict:
    import requests
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z]+)?", lang):
        raise SourceError("source_bad_link", lang)
    try:
        r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", timeout=20, headers={"User-Agent": UA},
                         params={"action": "query", "prop": "extracts", "explaintext": 1, "titles": title,
                                 "format": "json", "redirects": 1, "formatversion": 2})
        r.raise_for_status()
        page = (r.json().get("query", {}).get("pages") or [{}])[0]
    except requests.RequestException as e:
        raise SourceError("source_offline", type(e).__name__) from e
    except ValueError as e:
        raise SourceError("source_wikipedia_missing", "bad JSON") from e
    text = page.get("extract") or ""
    if page.get("missing") or not text.strip():
        raise SourceError("source_wikipedia_missing", title)
    # sections: "== Title ==" lines; drop reference-like sections
    blocks, keep = [], True
    for line in text.splitlines():
        m = re.match(r"^(=+)\s*(.*?)\s*=+$", line.strip())
        if m:
            keep = not _SKIP_SECTIONS.match(m.group(2))
            if keep:
                blocks.append(f"\n## {m.group(2)}")
            continue
        if keep and line.strip():
            blocks.append(line.strip())
    real = page.get("title") or title
    return {"kind": "wikipedia", "id": real, "lang": lang, "title": real,
            "url": f"https://{lang}.wikipedia.org/wiki/{real.replace(' ', '_')}", "blocks": blocks}


def fetch(source: str, link: str, lang: str = "fr") -> dict:
    """{'kind', 'title', 'url', 'lang', 'pages': [(file, part, text)]} for a YouTube or Wikipedia link.
    Raises SourceError (with an i18n key) when the link is wrong, the content is missing or there is no internet."""
    if source == "youtube":
        vid = youtube_id(link)
        if not vid:
            raise SourceError("source_bad_link", "not a YouTube link")
        key = f"youtube:{vid}"
    elif source == "wikipedia":
        wp = wikipedia_page(link, lang if lang in ("fr", "ar", "en") else "fr")
        if not wp:
            raise SourceError("source_bad_link", "not a Wikipedia link")
        key = f"wikipedia:{wp[0]}:{wp[1]}"
    else:
        raise SourceError("source_bad_link", source)
    d = _cached(key)
    if d is None:
        if llm.demo_mode():
            raise SourceError("source_offline", "demo mode: not fetched before")
        d = _fetch_youtube(vid, [lang, "fr", "ar", "en"]) if source == "youtube" else _fetch_wikipedia(*wp)
        _store(key, d)
    safe = re.sub(r"[^\w-]+", "_", d["id"]).strip("_")[:60]
    name = f"{d['kind']}-{safe}.txt"
    return {**{k: d[k] for k in ("kind", "title", "url", "lang")}, "pages": _parts(d["blocks"], name)}
