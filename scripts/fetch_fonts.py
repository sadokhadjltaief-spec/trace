"""Download the bundled fonts for PDFs and images (Latin + Arabic). SIL Open Font License 1.1.

Source: the google/fonts repository on GitHub (ofl/notosans, ofl/notonaskharabic). Writes assets/fonts/*.ttf
(gitignored) + the licence texts. Idempotent.
Usage: .\\.venv\\Scripts\\python.exe scripts\\fetch_fonts.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "fonts"
BASE = "https://github.com/google/fonts/raw/main/ofl"
FILES = {
    "NotoSans.ttf": f"{BASE}/notosans/NotoSans%5Bwdth,wght%5D.ttf",
    "NotoNaskhArabic.ttf": f"{BASE}/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    "OFL_NotoSans.txt": f"{BASE}/notosans/OFL.txt",
    "OFL_NotoNaskhArabic.txt": f"{BASE}/notonaskharabic/OFL.txt",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        p = OUT / name
        if p.exists() and p.stat().st_size > 1000:
            print("ok (cached)", name)
            continue
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
        p.write_bytes(data)
        print(f"downloaded {name} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
