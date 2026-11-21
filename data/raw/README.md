# Raw datasets: sources and licences

Everything in `data/raw/` except this file is gitignored. Rebuild it with
`.\.venv\Scripts\python.exe scripts\fetch_data.py` (the report goes to `data/raw/inspection_report.md`).

| Folder | Source | How fetched | Licence | Verified how |
|---|---|---|---|---|
| `map/` | MAP – Charting Student Math Misunderstandings | HF `kaggle-map/data` (the manual zip has the same three CSVs) | MIT | `license: mit` in the HF dataset card (`map/README.md`); the brief says the Kaggle data page says MIT too. I did not open the Kaggle page myself. |
| `eedi/` | Eedi – Mining Misconceptions in Mathematics (Kaggle 2024) | manual zip from Downloads (no Kaggle credentials on this machine) | **UNVERIFIED** | Web search did not turn up the competition's rules page. **Rule until verified: use locally only and do not publish derived files** (bank items copied from Eedi stay out of the public repo / slides). The NeurIPS 2020 Eedi data is CC BY-NC-ND 4.0, but that is a different dataset. **Action for the team:** open https://www.kaggle.com/competitions/eedi-mining-misconceptions-in-mathematics/rules and write the data-licence clause here. |
| `mathdial/` | MathDial (Macina et al., arXiv 2305.14536) | HF `eth-nlped/mathdial` | CC-BY-4.0 | `license: cc-by-4.0` in the HF dataset card |
| `otero/` | Otero, Druga, Lan, *A Benchmark for Math Misconceptions* (arXiv 2412.03765) | HF `nanote/algebra_misconceptions` | MIT | `license: mit` in the HF dataset card (read by the script *before* downloading). Used for taxonomy descriptions only. |

## Facts measured by the script (vs the brief's expectations)
- MAP `train.csv`: 36,696 rows, 15 QuestionIds, columns as expected. `test.csv` has 3 rows with no labels (placeholder).
- Eedi `train.csv`: **1,869** questions (the brief said about 1,857); all 1,869 have at least one labelled distractor; 1,604 distinct misconception IDs are used; `misconception_mapping.csv` has 2,587 rows (matches).
- MathDial: 2,262 train + 599 test dialogues (`.jsonl`).
- Otero: 220 examples in `data/data.json` (matches the paper's 220).
