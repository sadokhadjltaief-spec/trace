"""Every text I/O call in the repo must state encoding='utf-8' (Windows defaults to cp1252).

AST audit over all our Python files:
- open(...) in text mode, Path.read_text / write_text, pandas read_csv / read_json / to_csv / to_json,
  subprocess.run/check_output with text=True: all need an explicit `encoding=` keyword.
Plus a round-trip check that our UTF-8 data files contain non-cp1252 text (so a missing encoding WOULD fail).
"""
import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(p for d in ("engine", "eval", "scripts", "tests", "pages", "ui") for p in (ROOT / d).rglob("*.py")) \
    + [ROOT / "app.py"]

NEEDS_ENCODING_METHODS = {"read_text", "write_text", "read_csv", "read_json", "to_csv", "to_json"}


def _kw(call: ast.Call, name: str):
    return next((k for k in call.keywords if k.arg == name), None)


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def violations(path: Path) -> list[str]:
    out = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name is None or _kw(node, "encoding") is not None:
            continue
        if any(k.arg is None for k in node.keywords):  # **kwargs: cannot tell
            continue
        if name == "open" and isinstance(f, ast.Name):
            mode = _const(node.args[1]) if len(node.args) > 1 else _const(_kw(node, "mode").value) \
                if _kw(node, "mode") else "r"
            if isinstance(mode, str) and "b" in mode:
                continue
            out.append(f"{path.relative_to(ROOT)}:{node.lineno} open() without encoding")
        elif name in NEEDS_ENCODING_METHODS and isinstance(f, ast.Attribute):
            out.append(f"{path.relative_to(ROOT)}:{node.lineno} .{name}() without encoding")
        elif name in ("run", "check_output", "Popen") and _const(getattr(_kw(node, "text"), "value", None)) is True:
            out.append(f"{path.relative_to(ROOT)}:{node.lineno} subprocess {name}(text=True) without encoding")
    return out


def test_all_text_io_states_utf8():
    bad = [v for p in FILES for v in violations(p)]
    assert not bad, "missing encoding='utf-8':\n" + "\n".join(bad)


def test_audit_catches_a_violation(tmp_path):
    p = tmp_path / "x.py"
    p.write_text("from pathlib import Path\nPath('a').read_text()\nopen('b')\nopen('c', 'rb')\n", encoding="utf-8")
    global ROOT
    old, ROOT = ROOT, tmp_path
    try:
        assert len(violations(p)) == 2
    finally:
        ROOT = old


UTF8_FILES = [ROOT / "data" / "bank" / "bank.json", ROOT / "data" / "bank" / "review.md",
              *sorted((ROOT / "i18n").glob("*.json"))]


@pytest.mark.parametrize("path", [p for p in UTF8_FILES if p.exists()], ids=lambda p: p.name)
def test_data_files_are_utf8_and_break_under_cp1252(path):
    """These files hold French/Arabic text. They decode as UTF-8; read as cp1252 (the Windows default)
    they either fail or give mojibake. This is why every read must pass encoding='utf-8'."""
    raw = path.read_bytes()
    txt = raw.decode("utf-8")  # must not raise
    if path.suffix == ".json":
        json.loads(txt)
    if any(ord(c) > 127 for c in txt):
        try:
            wrong = raw.decode("cp1252")
        except UnicodeDecodeError:
            return  # the UnicodeDecodeError seen on Windows
        assert wrong != txt  # mojibake
