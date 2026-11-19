"""Corpus statistics after ingestion.

Prints, per doc_type: documents, pages, OCR pages, chunks, average chunk length; then the number of
chunks per concept. Saves everything to evaluation/results/corpus_stats.json.

    python scripts/corpus_stats.py                 # uses DATA_DIR from .env (default: data)
    python scripts/corpus_stats.py --ocr-samples 5 # also print 5 random OCR chunks (seeded)
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.concepts import CONCEPTS  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-samples", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "evaluation" / "results" / "corpus_stats.json")
    args = ap.parse_args()

    catalog = {d["doc_id"]: d for d in json.loads(settings.catalog_path.read_text("utf-8"))}
    manifest = json.loads((settings.processed_dir / "manifest.json").read_text("utf-8"))
    chunks = [json.loads(line) for line in
              (settings.processed_dir / "chunks.jsonl").read_text("utf-8").splitlines() if line.strip()]

    per_type: dict[str, dict] = defaultdict(lambda: {"documents": 0, "pages": 0, "ocr_pages": 0,
                                                     "chunks": 0, "_chars": 0})
    for doc_id, m in manifest.items():
        t = per_type[catalog[doc_id]["doc_type"]]
        t["documents"] += 1
        t["pages"] += m["pages"]
        t["ocr_pages"] += m["ocr_pages"]
    for c in chunks:
        t = per_type[c["metadata"]["doc_type"]]
        t["chunks"] += 1
        t["_chars"] += len(c["text"])

    total = {"documents": 0, "pages": 0, "ocr_pages": 0, "chunks": 0, "_chars": 0}
    for t in per_type.values():
        for k in total:
            total[k] += t[k]
    rows = {**dict(sorted(per_type.items())), "TOTAL": total}
    for t in rows.values():
        t["avg_chunk_chars"] = round(t.pop("_chars") / t["chunks"], 1) if t["chunks"] else 0.0

    concept_counts = Counter()
    for c in chunks:
        for cid in filter(None, c["metadata"]["concepts"].split(",")):
            concept_counts[cid] += 1
    per_concept = {cid: concept_counts.get(cid, 0) for cid in CONCEPTS}
    untagged = sum(1 for c in chunks if not c["metadata"]["concepts"])

    missing = sorted(set(catalog) - set(manifest))
    print(f"{'doc_type':<12}{'docs':>6}{'pages':>7}{'OCR':>6}{'chunks':>8}{'avg len':>9}")
    for name, t in rows.items():
        print(f"{name:<12}{t['documents']:>6}{t['pages']:>7}{t['ocr_pages']:>6}{t['chunks']:>8}"
              f"{t['avg_chunk_chars']:>9}")
    print(f"\ncatalog documents: {len(catalog)} | ingested: {len(manifest)} | missing: {missing or 'none'}")
    print("\nchunks per concept:")
    for cid, n in sorted(per_concept.items(), key=lambda kv: -kv[1]):
        print(f"  {cid:<32}{n:>6}")
    print(f"  {'(no concept)':<32}{untagged:>6}")

    out = {"catalog_documents": len(catalog), "ingested_documents": len(manifest),
           "missing_documents": missing, "chunk_size": settings.chunk_size,
           "chunk_overlap": settings.chunk_overlap, "per_doc_type": rows,
           "chunks_per_concept": per_concept, "chunks_without_concept": untagged}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
    print(f"\nsaved {args.out.relative_to(ROOT)}")

    if args.ocr_samples:
        ocr = [c for c in chunks if c["metadata"]["ocr"]]
        random.Random(args.seed).shuffle(ocr)
        for c in ocr[:args.ocr_samples]:
            m = c["metadata"]
            print(f"\n----- {c['chunk_id']} | {m['title']} | page {m['page']} -----\n{c['text']}")


if __name__ == "__main__":
    main()
