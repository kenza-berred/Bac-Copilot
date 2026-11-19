"""How much can we trust the LLM judge? Compare its correctness scores with yours.

    python evaluation/judge_agreement.py      # reads evaluation/data/human_check.jsonl
"""
from __future__ import annotations

from common import DATA, load_jsonl, save_results
from metrics import quadratic_weighted_kappa

rows = [r for r in load_jsonl(DATA / "human_check.jsonl") if r.get("human_correctness") is not None]
if not rows:
    raise SystemExit("Fill `human_correctness` in human_check.jsonl first.")
j = [round(r["judge_correctness"] * 2) for r in rows]
h = [round(r["human_correctness"] * 2) for r in rows]
res = {"n": len(rows), "exact_agreement": sum(a == b for a, b in zip(j, h)) / len(rows),
       "qwk": quadratic_weighted_kappa(j, h)}
print(res)
save_results("judge_agreement", res)
