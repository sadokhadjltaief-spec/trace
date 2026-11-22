"""YouTube / Wikipedia sources: link parsing, parts, cache, offline and demo-mode messages (network mocked)."""
from types import SimpleNamespace

import pytest

from engine import api, llm, practice, web_sources as ws


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "CACHE", tmp_path / "web")
    monkeypatch.setattr(llm, "_demo_mode", False)


@pytest.mark.parametrize("link,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"), ("https://youtu.be/dQw4w9WgXcQ?t=3", "dQw4w9WgXcQ"),
    ("youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"), ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&list=x", "dQw4w9WgXcQ"),
    ("https://example.com/watch?v=dQw4w9WgXcQ", None), ("pas un lien", None)])
def test_youtube_id(link, vid):
    assert ws.youtube_id(link) == vid


def test_wikipedia_page():
    assert ws.wikipedia_page("https://fr.wikipedia.org/wiki/Th%C3%A9or%C3%A8me_de_Pythagore") == ("fr", "Théorème de Pythagore")
    assert ws.wikipedia_page("https://ar.m.wikipedia.org/wiki/x#Section") == ("ar", "x")
    assert ws.wikipedia_page("Équation du second degré", "fr") == ("fr", "Équation du second degré")
    assert ws.wikipedia_page("https://example.com/a") is None


def fake_wiki(monkeypatch, calls):
    def get(lang, title):
        calls.append(title)
        return {"kind": "wikipedia", "id": title, "lang": lang, "title": title, "url": "https://fr.wikipedia.org/wiki/x",
                "blocks": ["Le théorème de Pythagore relie les côtés.", "\n## Énoncé", "a² + b² = c²." * 200]}
    monkeypatch.setattr(ws, "_fetch_wikipedia", get)


def test_wikipedia_parts_and_cache_then_offline_demo(monkeypatch):
    calls = []
    fake_wiki(monkeypatch, calls)
    got = ws.fetch("wikipedia", "https://fr.wikipedia.org/wiki/Th%C3%A9or%C3%A8me_de_Pythagore")
    assert got["pages"][0][0] == "wikipedia-Théorème_de_Pythagore.txt" and [p[1] for p in got["pages"]][:2] == [1, 2]
    monkeypatch.setattr(llm, "_demo_mode", True)                    # demo mode: cache only
    assert ws.fetch("wikipedia", "Théorème de Pythagore")["pages"] == got["pages"] and calls == ["Théorème de Pythagore"]
    with pytest.raises(ws.SourceError) as e:
        ws.fetch("wikipedia", "Thalès")
    assert e.value.key == "source_offline"


def test_practice_material_uses_the_source_and_explains_failures(monkeypatch):
    fake_wiki(monkeypatch, [])
    pages, why = practice.material([], "Théorème de Pythagore", "wikipedia", "fr")
    assert why is None and pages
    assert practice.material([], "https://example.com", "youtube", "fr") == ([], "source_bad_link")

    def offline(*a):
        raise ws.SourceError("source_offline", "ConnectionError")
    monkeypatch.setattr(ws, "_fetch_youtube", offline)
    pages, why = practice.material([], "https://youtu.be/dQw4w9WgXcQ", "youtube", "fr")
    assert why == "source_offline"
    r = api.practice_cards([], "https://youtu.be/dQw4w9WgXcQ", "youtube", "", "fr")
    assert not r["cards"] and "internet" in r["refused"]


def test_youtube_transcript_is_timestamped(monkeypatch):
    import youtube_transcript_api as yta

    snippets = [SimpleNamespace(text=f"phrase {i}", start=i * 10.0, duration=10) for i in range(9)]
    tr = SimpleNamespace(language_code="fr", fetch=lambda: snippets)
    listing = SimpleNamespace(find_manually_created_transcript=lambda langs: tr,
                              find_generated_transcript=lambda langs: tr, __iter__=lambda self: iter([tr]))
    monkeypatch.setattr(yta.YouTubeTranscriptApi, "list", lambda self, vid: listing)
    got = ws.fetch("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert got["pages"][0][0] == "youtube-dQw4w9WgXcQ.txt"
    assert got["pages"][0][2].startswith("[0:00] phrase 0") and "[0:40]" in got["pages"][0][2]
