"""Relevance annotation with pooling (standard IR practice).

For each question in eval_questions.jsonl that has no `relevant` passages yet, we pool the top-5
results of every retrieval mode, show them, and you type the numbers of the passages that really
answer the question. Annotations are saved after every question, so you can stop and resume.

    python evaluation/annotate.py
    python evaluation/annotate.py --redo q017     # re-annotate one question
"""
from __future__ import annotations

import argparse
from pathlib import Path

from common import DATA, load_jsonl, save_jsonl

from app.retrieval.hybrid import MODES, Retriever, rrf_fuse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DATA / "eval_questions.jsonl"))
    ap.add_argument("--redo", default=None)
    args = ap.parse_args()

    path = Path(args.file)
    rows = load_jsonl(path)
    retriever = Retriever.from_settings()
    for row in rows:
        if row.get("answerable") is False:
            continue
        if row.get("relevant") and row["id"] != args.redo:
            continue
        pools = [retriever.search(row["question"], k=5, mode=m) for m in MODES]
        pool = rrf_fuse(pools)[:12]
        print("\n" + "=" * 100)
        print(f"[{row['id']}] {row['question']}\n  concept={row.get('concept')}  référence: {row.get('reference_answer', '')[:200]}")
        for i, h in enumerate(pool, 1):
            m = h["metadata"]
            print(f"\n  ({i}) {m['title']} — p.{m['page']} {m['section']}\n      {h['text'][:350].replace(chr(10), ' ')}")
        ans = input("\nPassages pertinents (ex: 1 3), 's' pour passer, 'q' pour quitter : ").strip().lower()
        if ans == "q":
            break
        if ans == "s" or not ans:
            continue
        picked = [pool[int(x) - 1] for x in ans.split() if x.isdigit() and 0 < int(x) <= len(pool)]
        row["relevant"] = [{"doc_id": h["metadata"]["doc_id"], "page": h["metadata"]["page"]} for h in picked]
        save_jsonl(path, rows)
    done = sum(1 for r in rows if r.get("relevant"))
    print(f"\n{done}/{len(rows)} questions annotated.")


if __name__ == "__main__":
    main()
