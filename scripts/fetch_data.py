"""Fetch and inspect TRACE datasets. Idempotent; prints a report; never fails silently.

Usage:  .\.venv\Scripts\python.exe scripts\fetch_data.py
Writes: data/raw/<source>/..., data/raw/inspection_report.md
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REPORT: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    REPORT.append(msg)


def has_csv(d: Path) -> bool:
    return d.exists() and (any(d.rglob("*.csv")) or any(d.glob("*.jsonl")))


def try_hf_snapshot(repo_id: str, dest: Path) -> bool:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo_id=repo_id, repo_type="dataset", local_dir=str(dest),
                          token=os.getenv("HF_TOKEN") or None)
        ok = has_csv(dest) or any(dest.rglob("*.parquet")) or any(dest.glob("*.jsonl"))
        log(f"  HF {repo_id}: {'ok' if ok else 'downloaded but no csv/parquet found'}")
        return ok
    except Exception as e:  # noqa: BLE001 - report and fall through
        log(f"  HF {repo_id}: failed ({type(e).__name__}: {str(e)[:160]})")
        return False


def try_kaggle(comp: str, dest: Path) -> bool:
    kj = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".kaggle" / "kaggle.json"
    if not kj.exists() and not (os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")):
        log(f"  Kaggle {comp}: skipped (no kaggle.json and no KAGGLE_USERNAME/KAGGLE_KEY)")
        return False
    dest.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.executable).with_name("kaggle.exe")
    cmd = [str(exe) if exe.exists() else "kaggle", "competitions", "download", "-c", comp, "-p", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip()[:300]
        log(f"  Kaggle {comp}: failed: {msg}")
        if "403" in msg:
            log(f"  -> Accept the rules at https://www.kaggle.com/competitions/{comp}/rules then rerun.")
        return False
    for z in dest.glob("*.zip"):
        unzip(z, dest)
    return has_csv(dest)


def unzip(z: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        for m in zf.infolist():
            target = (dest / m.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):  # zip-slip guard
                raise ValueError(f"unsafe path in zip: {m.filename}")
        zf.extractall(dest)


def try_manual_zip(pattern: str, dest: Path) -> bool:
    zips = sorted(RAW.glob(pattern))
    if not zips:
        log(f"  manual zip {pattern}: none in data/raw/")
        return False
    unzip(zips[0], dest)
    log(f"  manual zip: extracted {zips[0].name} -> {dest.relative_to(ROOT)}")
    return has_csv(dest)


def fetch(name: str, dest: Path, steps) -> bool:
    log(f"\n## Fetch {name}")
    if has_csv(dest):
        log(f"  already present in {dest.relative_to(ROOT)} (skipping download)")
        return True
    for step in steps:
        if step():
            return True
    log(f"  !! {name}: NO SOURCE WORKED")
    return False


def inspect_csv(p: Path) -> pd.DataFrame:
    df = pd.read_csv(p, encoding="utf-8")
    log(f"\n### {p.relative_to(ROOT)}")
    log(f"rows={len(df)} cols={len(df.columns)}")
    log("| column | dtype | missing |\n|---|---|---|")
    for c in df.columns:
        log(f"| {c} | {df[c].dtype} | {int(df[c].isna().sum())} |")
    log("\n5 random rows:\n```")
    with pd.option_context("display.max_colwidth", 80, "display.width", 200):
        log(df.sample(min(5, len(df)), random_state=0).to_string())
    log("```")
    return df


def inspect_map(d: Path) -> None:
    log("\n## Inspect MAP")
    for p in sorted(d.rglob("*.csv")):
        df = inspect_csv(p)
        if "Category" in df.columns:
            log("\nCategory counts:\n```\n" + df["Category"].value_counts(dropna=False).to_string() + "\n```")
        if "Misconception" in df.columns:
            log("\nMisconception counts:\n```\n" + df["Misconception"].value_counts(dropna=False).to_string() + "\n```")
        if "QuestionId" in df.columns:
            log(f"\ndistinct QuestionId: {df['QuestionId'].nunique()}")
            labelled = "Category" in df.columns
            log(f"holds labels: {labelled}")
            if labelled:
                g = df.groupby("QuestionId").agg(n=("row_id", "size"),
                                                 text=("QuestionText", "first"))
                misc = df.dropna(subset=["Misconception"]).groupby("QuestionId")["Misconception"] \
                    .agg(lambda s: ", ".join(f"{k}({v})" for k, v in s.value_counts().items()))
                g["misconceptions"] = misc
                with pd.option_context("display.max_colwidth", 120, "display.width", 250):
                    log("\nPer question:\n```\n" + g.to_string() + "\n```")


def inspect_eedi(d: Path) -> None:
    log("\n## Inspect Eedi")
    frames = {p.name: inspect_csv(p) for p in sorted(d.rglob("*.csv"))}
    train = next((v for k, v in frames.items() if k.lower().startswith("train")), None)
    mm = next((v for k, v in frames.items() if "misconception_mapping" in k.lower()), None)
    if train is None:
        log("  no train csv found")
        return
    mcols = [c for c in train.columns if c.startswith("Misconception") and c.endswith("Id")]
    labelled = train[mcols].notna().any(axis=1)
    log(f"\nquestions: {len(train)}; with >=1 labelled distractor: {int(labelled.sum())}")
    ids = pd.unique(train[mcols].values.ravel())
    ids = [i for i in ids if pd.notna(i)]
    log(f"unique misconception ids used in train: {len(ids)}")
    if mm is not None:
        log(f"misconception_mapping rows: {len(mm)}")
        names = dict(zip(mm.iloc[:, 0], mm.iloc[:, 1]))
        log("\n3 complete example questions:")
        for _, r in train[labelled].sample(3, random_state=1).iterrows():
            log(f"\n- Q{r['QuestionId']} [{r.get('SubjectName', '')} / {r.get('ConstructName', '')}]")
            log(f"  {r['QuestionText']}")
            for L in "ABCD":
                mid = r.get(f"Misconception{L}Id")
                tag = "  (correct)" if r.get("CorrectAnswer") == L else (
                    f"  -> [{int(mid)}] {names.get(int(mid), '?')}" if pd.notna(mid) else "")
                log(f"  {L}: {r.get(f'Answer{L}Text')}{tag}")
    if "SubjectName" in train.columns:
        log("\nTop 25 SubjectName:\n```\n" + train["SubjectName"].value_counts().head(25).to_string() + "\n```")


def inspect_mathdial(d: Path) -> None:
    log("\n## Inspect MathDial")
    files = sorted(list(d.rglob("*.csv")) + list(d.rglob("*.parquet")) + list(d.rglob("*.jsonl")))
    for p in files:
        log(f"  {p.relative_to(ROOT)} ({p.stat().st_size // 1024} KB)")
    for p in [f for f in files if f.suffix == ".jsonl"]:
        df = pd.read_json(p, lines=True, encoding="utf-8")
        log(f"  {p.name}: rows={len(df)} cols={list(df.columns)}")
        log(f"  example question: {str(df.iloc[0]['question'])[:200]}")
        log(f"  example conversation start: {str(df.iloc[0]['conversation'])[:300]}")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    log("# TRACE data fetch + inspection report")

    map_d, eedi_d, md_d = RAW / "map", RAW / "eedi", RAW / "mathdial"
    ok_map = fetch("MAP", map_d, [
        lambda: try_hf_snapshot("kaggle-map/data", map_d),
        lambda: try_kaggle("map-charting-student-math-misunderstandings", map_d),
        lambda: try_manual_zip("map-charting-student-math-misunderstandings*.zip", map_d),
    ])
    ok_eedi = fetch("Eedi", eedi_d, [
        lambda: try_kaggle("eedi-mining-misconceptions-in-mathematics", eedi_d),
        lambda: try_manual_zip("eedi-mining-misconceptions-in-mathematics*.zip", eedi_d),
    ])
    ok_md = fetch("MathDial", md_d, [lambda: try_hf_snapshot("eth-nlped/mathdial", md_d)])
    log("\n## Fetch Otero et al. algebra misconceptions (arXiv 2412.03765)")
    ot_d = RAW / "otero"
    try:  # licence check on the dataset card BEFORE downloading the data files
        from huggingface_hub import hf_hub_download
        card = Path(hf_hub_download("nanote/algebra_misconceptions", "README.md",
                                    repo_type="dataset", local_dir=str(ot_d))).read_text(encoding="utf-8")
        lic = next((ln.split(":", 1)[1].strip() for ln in card.splitlines()
                    if ln.strip().startswith("license:")), "unknown")
        log(f"  nanote/algebra_misconceptions card licence: {lic}")
        if lic.lower() == "mit":
            try_hf_snapshot("nanote/algebra_misconceptions", ot_d)
            files = [p for p in ot_d.rglob("*") if p.is_file() and ".cache" not in p.parts]
            log(f"    {len(files)} files ({sum(p.suffix == '.txt' for p in files)} .txt examples)")
            dj = ot_d / "data" / "data.json"
            if dj.exists():
                import json
                d = json.loads(dj.read_text(encoding="utf-8"))
                log(f"    data/data.json: type={type(d).__name__} len={len(d)}")
        else:
            log("  licence not MIT: data files NOT downloaded")
    except Exception as e:  # noqa: BLE001
        log(f"  Otero fetch failed ({type(e).__name__}: {str(e)[:160]})")

    if ok_map:
        inspect_map(map_d)
    if ok_eedi:
        inspect_eedi(eedi_d)
    if ok_md:
        inspect_mathdial(md_d)

    log(f"\n## Summary\nMAP={ok_map} Eedi={ok_eedi} MathDial={ok_md}")
    (RAW / "inspection_report.md").write_text("\n".join(REPORT), encoding="utf-8")
    print(f"\nReport written to {RAW / 'inspection_report.md'}")
    if not (ok_map and ok_eedi):
        sys.exit(1)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
