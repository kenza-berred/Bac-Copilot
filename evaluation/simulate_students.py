"""Does adaptive practice help? A simulation with virtual students.

Each virtual student has a hidden true state (known / not known) for every SVT concept.
A concept can only be learned if its prerequisites are known (that's what the concept graph
encodes). At each step, a policy chooses which concept to practise; the student answers
(with slip/guess noise), may learn the concept, and our StudentModel is updated with the result.

Policies compared over the same number of practice questions:
  - random     : random concept
  - sequential : follow the curriculum order
  - adaptive   : StudentModel.recommend() (BKT + spaced repetition + prerequisites first)

Metric: share of concepts truly mastered after N questions (averaged over students).

    python evaluation/simulate_students.py --students 200 --steps 60
"""
from __future__ import annotations

import argparse
import random
import statistics
import tempfile
from pathlib import Path

from common import markdown_table, save_results

from app.concepts import CONCEPTS
from app.student.model import StudentModel

SLIP, GUESS, LEARN = 0.1, 0.2, 0.3
ORDER = list(CONCEPTS)


def run_student(policy: str, sid: str, sm: StudentModel, steps: int, rng: random.Random) -> float:
    known = {c: rng.random() < 0.15 and not CONCEPTS[c].prerequisites for c in CONCEPTS}
    for step in range(steps):
        if policy == "random":
            c = rng.choice(ORDER)
        elif policy == "sequential":
            c = next((x for x in ORDER if not known[x]), ORDER[step % len(ORDER)])
            # a real "sequential" student doesn't know `known`; use the model's estimate instead
            c = next((x for x in ORDER if sm._row(sid, x)["p_know"] < 0.8), ORDER[step % len(ORDER)])
        else:
            c = sm.recommend(sid, n=1)[0]["concept"]
        correct = (rng.random() > SLIP) if known[c] else (rng.random() < GUESS)
        sm.record_attempt(sid, c, float(correct), 1.0)
        prereqs_ok = all(known[p] for p in CONCEPTS[c].prerequisites)
        if not known[c] and prereqs_ok and rng.random() < LEARN:
            known[c] = True
    return sum(known.values()) / len(known)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=200)
    ap.add_argument("--steps", type=int, default=60)
    args = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for policy in ("random", "sequential", "adaptive"):
            sm = StudentModel(Path(tmp) / f"{policy}.sqlite")
            rng = random.Random(7)  # same students for every policy
            scores = [run_student(policy, f"{policy}-{i}", sm, args.steps, rng) for i in range(args.students)]
            rows.append({"policy": policy, "students": args.students, "steps": args.steps,
                         "mastered_share": statistics.mean(scores), "std": statistics.pstdev(scores)})
            print(f"{policy:<10} mastered={rows[-1]['mastered_share']:.3f}")
    print("\n" + markdown_table(rows, ["policy", "students", "steps", "mastered_share", "std"]))
    save_results("simulation", {"results": rows, "params": {"slip": SLIP, "guess": GUESS, "learn": LEARN}})


if __name__ == "__main__":
    main()
