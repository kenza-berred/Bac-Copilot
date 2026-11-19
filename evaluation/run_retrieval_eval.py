"""Retrieval benchmark: Recall@k, Hit@k, MRR and nDCG@k for each retrieval mode.

    python evaluation/run_retrieval_eval.py
    python evaluation/run_retrieval_eval.py --modes dense hybrid --by-language

Chunk-size ablation: re-ingest into another DATA_DIR with a different CHUNK_SIZE, e.g.
    DATA_DIR=data_c500 CHUNK_SIZE=500 python -m app.ingestion.pipeline   (from backend/)
    DATA_DIR=data_c500 python evaluation/run_retrieval_eval.py --tag c500
"""
from __future__ import annotations

import argparse
import statistics
import time
from collections import defaultdict

from common import DATA, load_jsonl, markdown_table, save_results
from metrics import hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank

from app.config import settings
from app.retrieval.hybrid import MODES, Retriever

KS = (1, 3, 5, 10)


def evaluate(retriever: Retriever, questions: list[dict], mode: str) -> tuple[dict, list[dict]]:
    per_q, latencies = [], []
    for q in questions:
        t0 = time.perf_counter()
        hits = retriever.search(q["question"], k=max(KS), mode=mode)
        latencies.append(time.perf_counter() - t0)
        row = {"id": q["id"], "language": q.get("language", "fr"), "concept": q.get("concept"),
               "mrr": reciprocal_rank(hits, q["relevant"])}
        for k in KS:
            row[f"recall@{k}"] = recall_at_k(hits, q["relevant"], k)
            row[f"hit@{k}"] = hit_at_k(hits, q["relevant"], k)
        row["ndcg@5"] = ndcg_at_k(hits, q["relevant"], 5)
        per_q.append(row)
    summary = {"mode": mode, "n": len(per_q)}
    for key in [f"recall@{k}" for k in KS] + ["hit@5", "mrr", "ndcg@5"]:
        summary[key] = statistics.mean(r[key] for r in per_q)
    summary["latency_ms"] = 1000 * statistics.median(latencies)
    return summary, per_q


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=list(MODES))
    ap.add_argument("--by-language", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    questions = [q for q in load_jsonl(DATA / "eval_questions.jsonl") if q.get("relevant")]
    if len(questions) < 10:
        raise SystemExit(f"Only {len(questions)} annotated questions — run evaluation/annotate.py first.")
    retriever = Retriever.from_settings()

    summaries, details = [], {}
    for mode in args.modes:
        s, per_q = evaluate(retriever, questions, mode)
        summaries.append(s)
        details[mode] = per_q
        print(f"{mode:<14} R@5={s['recall@5']:.3f} MRR={s['mrr']:.3f} nDCG@5={s['ndcg@5']:.3f}")

    cols = ["mode", "n", "recall@1", "recall@3", "recall@5", "recall@10", "mrr", "ndcg@5", "latency_ms"]
    print("\n" + markdown_table(summaries, cols))

    if args.by_language:
        rows = []
        for mode, per_q in details.items():
            groups = defaultdict(list)
            for r in per_q:
                groups[r["language"]].append(r)
            for lang, rs in groups.items():
                rows.append({"mode": mode, "language": lang, "n": len(rs),
                             "recall@5": statistics.mean(r["recall@5"] for r in rs),
                             "mrr": statistics.mean(r["mrr"] for r in rs)})
        print(markdown_table(rows, ["mode", "language", "n", "recall@5", "mrr"]))

    path = save_results(f"retrieval{'_' + args.tag if args.tag else ''}", {
        "config": {"embedding": settings.embedding_model, "reranker": settings.reranker_model,
                   "chunk_size": settings.chunk_size, "chunk_overlap": settings.chunk_overlap},
        "summary": summaries, "per_question": details})
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
