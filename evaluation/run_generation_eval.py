"""Answer-generation benchmark (LLM-as-judge + deterministic citation checks).

Compares two systems on the same questions:
  - baseline  : plain RAG (retrieve top-6 -> answer), no verification loop
  - agent     : the full LangGraph agent (routing, citation verification, retry)

Metrics per answer:
  - faithfulness       (judge, 0-1): share of claims supported by the retrieved excerpts
  - correctness        (judge, 0/1/2 -> 0/0.5/1): agreement with the reference answer
  - citation_valid     : every [n] points to an existing excerpt
  - citation_precision : share of cited excerpts that are annotated as relevant (if annotated)
  - refusal_ok         : for `answerable: false` questions, did the system say it doesn't know?
  - latency

Resumable: every scored answer is appended to evaluation/results/generation_cache.jsonl.
Re-running the same command skips what is already done. On Groq's free tier
(8K tokens/minute, 200K tokens/day per model) the script waits when the per-minute limit is hit,
and stops cleanly when the daily limit is hit: just re-run it the next day.

The judge runs on GROQ_FAST_MODEL by default (--judge fast), which has its own daily quota,
so answers (main model) and judging (fast model) don't compete for the same budget.

Validate the judge: export a sample with --export-human, grade it yourself, then
`python evaluation/judge_agreement.py` reports judge-vs-human agreement.

    python evaluation/run_generation_eval.py                  # all 64 questions, both systems
    python evaluation/run_generation_eval.py --sample 30      # stratified subset (faster)
    python evaluation/run_generation_eval.py --export-human 30
    python evaluation/run_generation_eval.py --fresh          # ignore the cache and start over
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time

from pydantic import BaseModel

from common import DATA, RESULTS, load_jsonl, markdown_table, save_jsonl, save_results
from metrics import is_relevant

from app.agent import prompts as P
from app.agent.graph import cited_numbers, format_context
from app.llm import get_llm, invoke_json, invoke_text
from app.services import get_agent, get_retriever

CACHE = RESULTS / "generation_cache.jsonl"
METRICS = ("faithfulness", "correctness", "citation_valid", "citation_precision", "refusal_ok", "latency_s")

JUDGE_SYSTEM = """Tu es un évaluateur strict de réponses pour un assistant de révision de SVT (bac tunisien).
On te donne : la question, les extraits récupérés, la réponse de référence et la réponse du système.
1. faithfulness : liste les affirmations factuelles de la réponse ; quelle proportion est soutenue par les extraits ? (0 à 1)
2. correctness : 2 = correcte et complète par rapport à la référence, 1 = partiellement, 0 = fausse ou hors sujet.
3. refused : la réponse dit-elle qu'elle ne trouve pas l'information ? (true/false)
Réponds UNIQUEMENT en JSON : {"faithfulness": 0.0, "correctness": 0, "refused": false, "comment": "..."}"""


class Judgement(BaseModel):
    faithfulness: float
    correctness: int
    refused: bool = False
    comment: str = ""


class DailyQuotaReached(Exception):
    pass


def with_backoff(fn, *args, tries: int = 6, wait_s: int = 65):
    """Retry on Groq per-minute rate limits; raise DailyQuotaReached on the per-day limit."""
    for attempt in range(tries):
        try:
            return fn(*args)
        except Exception as e:  # groq.RateLimitError, httpx errors, ...
            msg = str(e).lower()
            if "per day" in msg or "tpd" in msg or "rpd" in msg:
                raise DailyQuotaReached(str(e)) from e
            if "429" in msg or "rate limit" in msg or "rate_limit" in msg:
                print(f"    rate limit (per minute) — waiting {wait_s}s ({attempt + 1}/{tries})", flush=True)
                time.sleep(wait_s)
                continue
            raise
    raise RuntimeError("still rate-limited after several retries")


def baseline_answer(question: str) -> tuple[str, list[dict]]:
    docs = get_retriever().search(question, k=6)
    text = invoke_text(get_llm(), P.ANSWER_SYSTEM.format(language="fr"),
                       P.ANSWER_USER.format(context=format_context(docs), history="—", question=question))
    return text, docs


def agent_answer(question: str) -> tuple[str, list[dict]]:
    out = get_agent().run(student_id="eval", intent="ask", message=question, search_query=question)
    return out["answer"], out["docs"]


SYSTEMS = {"baseline": baseline_answer, "agent": agent_answer}


def judge(q: dict, answer: str, docs: list[dict], fast: bool) -> Judgement:
    user = (f"Question : {q['question']}\n\nExtraits :\n{format_context(docs)}\n\n"
            f"Référence : {q.get('reference_answer') or '—'}\n\nRéponse du système :\n{answer}")
    return invoke_json(get_llm(fast=fast, temperature=0.0), JUDGE_SYSTEM, user, Judgement)


def score(q: dict, answer: str, docs: list[dict], fast_judge: bool) -> dict:
    j = with_backoff(judge, q, answer, docs, fast_judge)
    nums = cited_numbers(answer)
    valid = all(1 <= n <= len(docs) for n in nums)
    row = {"id": q["id"], "language": q.get("language", "fr"), "faithfulness": j.faithfulness,
           "correctness": j.correctness / 2, "citation_valid": float(valid and bool(nums or j.refused)),
           "refused": j.refused, "comment": j.comment}
    if q.get("relevant") and nums:
        cited = [docs[n - 1] for n in nums if 1 <= n <= len(docs)]
        row["citation_precision"] = sum(is_relevant(d["metadata"], q["relevant"]) for d in cited) / max(len(cited), 1)
    if q.get("answerable") is False:
        row["refusal_ok"] = float(j.refused)
    return row


def stratified_sample(questions: list[dict], n: int) -> list[dict]:
    """Keep every out-of-scope and non-French question, fill the rest with French ones (fixed seed)."""
    keep = [q for q in questions if q.get("answerable") is False or q.get("language", "fr") != "fr"]
    rest = [q for q in questions if q not in keep]
    random.Random(42).shuffle(rest)
    chosen = {q["id"] for q in keep + rest[: max(n - len(keep), 0)]}
    return [q for q in questions if q["id"] in chosen]


def load_cache() -> dict[tuple[str, str], dict]:
    if not CACHE.exists():
        return {}
    return {(r["system"], r["id"]): r for r in load_jsonl(CACHE)}


def append_cache(row: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(name: str, rows: list[dict]) -> dict:
    s = {"system": name, "n": len(rows)}
    for key in METRICS:
        vals = [r[key] for r in rows if key in r]
        s[key] = statistics.mean(vals) if vals else float("nan")
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="first N questions only")
    ap.add_argument("--sample", type=int, default=None, help="stratified subset of N questions")
    ap.add_argument("--systems", nargs="+", default=["baseline", "agent"])
    ap.add_argument("--judge", choices=["fast", "main"], default="fast")
    ap.add_argument("--export-human", type=int, default=0, help="export N answers for human grading")
    ap.add_argument("--fresh", action="store_true", help="delete the cache and start over")
    args = ap.parse_args()

    questions = load_jsonl(DATA / "eval_questions.jsonl")
    if args.limit:
        questions = questions[: args.limit]
    if args.sample:
        questions = stratified_sample(questions, args.sample)
    if args.fresh and CACHE.exists():
        CACHE.unlink()
    cache = load_cache()

    stopped = None
    try:
        # Interleave systems per question so a partial run still compares both on the same questions.
        for q in questions:
            for name in args.systems:
                if (name, q["id"]) in cache:
                    continue
                t0 = time.perf_counter()
                answer, docs = with_backoff(SYSTEMS[name], q["question"])
                latency = time.perf_counter() - t0
                row = score(q, answer, docs, fast_judge=args.judge == "fast")
                row.update({"system": name, "latency_s": latency, "answer": answer,
                            "question": q["question"], "reference": q.get("reference_answer")})
                append_cache(row)
                cache[(name, q["id"])] = row
                print(f"[{name}] {q['id']}: faith={row['faithfulness']:.2f} corr={row['correctness']:.1f}", flush=True)
    except DailyQuotaReached as e:
        stopped = str(e)
    except KeyboardInterrupt:
        stopped = "interrupted"

    ids = {q["id"] for q in questions}
    # Only compare on questions both systems have finished, so the comparison stays fair.
    done_ids = {i for i in ids if all((s, i) in cache for s in args.systems)}
    summaries, details = [], {}
    for name in args.systems:
        rows = [cache[(name, i)] for i in sorted(done_ids)]
        details[name] = rows
        summaries.append(summarize(name, rows))

    print(f"\n{len(done_ids)}/{len(ids)} questions completed by every system.")
    if summaries and done_ids:
        print("\n" + markdown_table(summaries, ["system", "n", *METRICS]))
        by_lang = []
        for name in args.systems:
            for lang in sorted({r["language"] for r in details[name]}):
                rs = [r for r in details[name] if r["language"] == lang]
                by_lang.append({"system": name, "language": lang, "n": len(rs),
                                "faithfulness": statistics.mean(r["faithfulness"] for r in rs),
                                "correctness": statistics.mean(r["correctness"] for r in rs)})
        print(markdown_table(by_lang, ["system", "language", "n", "faithfulness", "correctness"]))
        save_results("generation", {"complete": len(done_ids) == len(ids), "n_done": len(done_ids),
                                    "n_planned": len(ids), "judge": args.judge,
                                    "summary": summaries, "by_language": by_lang, "per_question": details})

    if args.export_human and done_ids:
        export = [{"system": r["system"], "id": r["id"], "question": r["question"], "reference": r["reference"],
                   "answer": r["answer"], "judge_correctness": r["correctness"], "human_correctness": None}
                  for name in args.systems for r in details[name]]
        random.seed(0)
        save_jsonl(DATA / "human_check.jsonl", random.sample(export, min(args.export_human, len(export))))
        print("Exported human_check.jsonl — fill `human_correctness` (0, 0.5, 1) then run judge_agreement.py")

    if stopped:
        print(f"\nStopped early ({stopped[:160]}).\nProgress is saved in {CACHE} — re-run the same command later to continue.")
        sys.exit(2)


if __name__ == "__main__":
    main()
