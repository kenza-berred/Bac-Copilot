"""Draft the grading benchmark from official bac corrigés.

For N passages taken from `bac_corrige` documents, the LLM extracts one question with its official
answer and barème, then writes 4 student answers of different quality (excellent, partial,
misconception, off-topic). YOU then grade every answer with the official barème and fill
`human_score` — those human grades are the ground truth of run_grading_eval.py.

    python evaluation/make_grading_set.py --n 20
    # then edit evaluation/data/grading_set.jsonl (human_score: null -> your grade)
"""
from __future__ import annotations

import argparse
import random

from pydantic import BaseModel

from common import DATA, save_jsonl

from app.concepts import CONCEPTS
from app.llm import get_llm, invoke_json
from app.retrieval.store import ChunkRecords
from app.config import settings

SYSTEM = """À partir de cet extrait de corrigé officiel du bac tunisien de SVT, extrais UNE question de
restitution des connaissances ou d'analyse, avec sa réponse officielle et son barème.
Puis écris 4 réponses d'élèves de qualités différentes :
  "excellent" (complète), "partial" (incomplète), "misconception" (contient une erreur conceptuelle typique),
  "off_topic" (hors sujet ou très faible). Style d'un élève de terminale tunisien, en français.
Concepts autorisés : {concepts}
Réponds UNIQUEMENT en JSON :
{{"question": "...", "reference": "...", "rubric": [{{"criterion": "...", "points": 1.0}}], "concept": "id",
  "answers": {{"excellent": "...", "partial": "...", "misconception": "...", "off_topic": "..."}}}}"""


class Draft(BaseModel):
    question: str
    reference: str
    rubric: list[dict]
    concept: str | None = None
    answers: dict[str, str]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()
    records = [r for r in ChunkRecords(settings.processed_dir / "chunks.jsonl").all()
               if r["metadata"]["doc_type"] == "bac_corrige" and len(r["text"]) > 300]
    if not records:
        raise SystemExit("No bac corrigé chunks indexed — download and ingest the bac exams first.")
    random.seed(1)
    picks = random.sample(records, min(args.n, len(records)))
    concepts = ", ".join(CONCEPTS)
    rows = []
    for i, rec in enumerate(picks, 1):
        try:
            d = invoke_json(get_llm(temperature=0.7), SYSTEM.format(concepts=concepts),
                            f"Source : {rec['metadata']['title']}, p.{rec['metadata']['page']}\n\n{rec['text']}",
                            Draft)
        except ValueError as e:
            print(f"skip {rec['chunk_id']}: {e}")
            continue
        max_score = sum(float(r.get("points", 0)) for r in d.rubric) or 2.0
        for quality, answer in d.answers.items():
            rows.append({"id": f"g{i:03d}-{quality}", "question": d.question,
                         "concept": d.concept if d.concept in CONCEPTS else None,
                         "rubric": d.rubric, "reference": d.reference, "student_answer": answer,
                         "quality_intended": quality, "max_score": max_score, "human_score": None,
                         "source": {"doc_id": rec["metadata"]["doc_id"], "page": rec["metadata"]["page"]}})
        print(f"[{i}/{len(picks)}] {d.question[:80]}")
    save_jsonl(DATA / "grading_set.jsonl", rows)
    print(f"Wrote {len(rows)} answers. Now grade them yourself: fill every `human_score`.")


if __name__ == "__main__":
    main()
