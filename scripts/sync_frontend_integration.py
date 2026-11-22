"""Copy the frontend files that TRACE created or modified (C:\\TRACE_frontend_temp, not a git repository) into
frontend_integration/ so they are versioned with the engine. Originals of modified files: _backup_avant_trace/.
Usage: .\\.venv\\Scripts\\python.exe scripts\\sync_frontend_integration.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

FRONT = Path(r"C:\TRACE_frontend_temp")
OUT = Path(__file__).resolve().parents[1] / "frontend_integration"
FILES = [
    "next.config.mjs",
    "app/api/chat/route.ts",
    "app/api/study-plan/route.ts",
    "components/dashboard/tutor/use-trace-chat.ts",
    "components/dashboard/tutor/tutor-chat.tsx",
    "components/dashboard/tutor/tutor-copy.ts",
    "components/dashboard/preparation-experience.tsx",
    "components/dashboard/study-plan-flow.tsx",
    "components/dashboard/quiz-source-picker.tsx",
    "components/dashboard/quiz-player.tsx",
    "components/dashboard/flashcard-player.tsx",
    "components/dashboard/study-plan-session.tsx",
]


def main() -> int:
    n = 0
    for f in FILES:
        src = FRONT / f
        if src.exists():
            dst = OUT / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    (OUT / "README.md").write_text(
        "# Frontend integration (copy)\n\nFiles of the Next.js app (`C:\\TRACE_frontend_temp`, not a git repository) "
        "that TRACE created or modified to connect it to the engine. Same paths as in the app. The originals of the "
        "modified files are in the app's `_backup_avant_trace/` folder.\n", encoding="utf-8")
    print(f"copied {n} files to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
