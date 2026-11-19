"""Knowledge-tracing benchmark: does our BKT student model predict the next answer?

Dataset: ASSISTments 2009-2010 "skill builder" (public, real students). Download the CSV
(skill_builder_data.csv) from the ASSISTments datasets page and pass it with --csv.
Columns used: user_id, skill_name, correct, order_id.

Compared models (AUC and RMSE on the next-answer prediction, 80/20 split by student):
  - global mean          : always predict the overall success rate
  - per-skill mean       : success rate of the skill on the training students
  - BKT (default params) : the parameters used in the app
  - BKT (fitted)         : per-skill parameters fitted by grid search on the training students

    python evaluation/run_kt_eval.py --csv path/to/skill_builder_data.csv
    python evaluation/run_kt_eval.py --synthetic   # sanity check without the dataset
"""
from __future__ import annotations

import argparse
import csv
import itertools
import random
from collections import defaultdict

import numpy as np
from sklearn.metrics import roc_auc_score

from common import markdown_table, save_results

from app.student.model import BKTParams, bkt_update, p_correct

GRID = [BKTParams(p_init=a, p_learn=b, p_slip=c, p_guess=d)
        for a, b, c, d in itertools.product((0.1, 0.3, 0.5), (0.05, 0.15, 0.3), (0.05, 0.1, 0.2), (0.1, 0.2, 0.3))]


def load_assistments(path: str, max_students: int | None) -> dict[str, list[tuple[str, int]]]:
    seqs: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    with open(path, encoding="latin-1") as f:
        for row in csv.DictReader(f):
            if not row.get("skill_name"):
                continue
            seqs[row["user_id"]].append((int(row["order_id"]), row["skill_name"], int(row["correct"])))
    users = list(seqs)[:max_students] if max_students else list(seqs)
    return {u: [(s, c) for _, s, c in sorted(seqs[u])] for u in users}


def synthetic(n_students=400, skills=8, length=40, seed=0) -> dict[str, list[tuple[str, int]]]:
    rng = random.Random(seed)
    data = {}
    for u in range(n_students):
        known = {f"s{k}": rng.random() < 0.2 for k in range(skills)}
        seq = []
        for _ in range(length):
            s = f"s{rng.randrange(skills)}"
            correct = (rng.random() > 0.1) if known[s] else (rng.random() < 0.25)
            seq.append((s, int(correct)))
            if not known[s] and rng.random() < 0.15:
                known[s] = True
        data[str(u)] = seq
    return data


def bkt_predictions(seqs, params_for) -> tuple[list[float], list[int]]:
    preds, ys = [], []
    for seq in seqs.values():
        state: dict[str, float] = {}
        for skill, y in seq:
            prm = params_for(skill)
            p = state.get(skill, prm.p_init)
            preds.append(p_correct(p, prm))
            ys.append(y)
            state[skill] = bkt_update(p, float(y), prm)
    return preds, ys


def fit_per_skill(train) -> dict[str, BKTParams]:
    by_skill: dict[str, dict] = defaultdict(dict)
    for u, seq in train.items():
        for skill, y in seq:
            by_skill[skill].setdefault(u, []).append((skill, y))
    fitted = {}
    for skill, seqs in by_skill.items():
        best, best_ll = None, -1e18
        for prm in GRID:
            p, y = bkt_predictions(seqs, lambda _s: prm)
            p = np.clip(p, 1e-4, 1 - 1e-4)
            ll = float(np.sum(np.array(y) * np.log(p) + (1 - np.array(y)) * np.log(1 - p)))
            if ll > best_ll:
                best, best_ll = prm, ll
        fitted[skill] = best
    return fitted


def metrics(name, preds, ys) -> dict:
    preds, ys = np.array(preds), np.array(ys)
    auc = roc_auc_score(ys, preds) if len(set(ys)) > 1 and preds.std() > 0 else 0.5
    return {"model": name, "n": int(len(ys)), "auc": float(auc), "rmse": float(np.sqrt(np.mean((preds - ys) ** 2)))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--max-students", type=int, default=2000)
    args = ap.parse_args()
    if not args.csv and not args.synthetic:
        raise SystemExit("--csv path/to/skill_builder_data.csv or --synthetic")

    data = synthetic() if args.synthetic else load_assistments(args.csv, args.max_students)
    users = sorted(data)
    random.Random(42).shuffle(users)
    cut = int(0.8 * len(users))
    train, test = {u: data[u] for u in users[:cut]}, {u: data[u] for u in users[cut:]}

    all_train = [y for seq in train.values() for _, y in seq]
    gmean = float(np.mean(all_train))
    skill_mean = defaultdict(list)
    for seq in train.values():
        for s, y in seq:
            skill_mean[s].append(y)
    skill_mean = {s: float(np.mean(v)) for s, v in skill_mean.items()}
    ys = [y for seq in test.values() for _, y in seq]

    rows = [metrics("global mean", [gmean] * len(ys), ys),
            metrics("per-skill mean", [skill_mean.get(s, gmean) for seq in test.values() for s, _ in seq], ys)]
    rows.append(metrics("BKT default", *bkt_predictions(test, lambda s: BKTParams())))
    fitted = fit_per_skill(train)
    rows.append(metrics("BKT fitted", *bkt_predictions(test, lambda s: fitted.get(s, BKTParams()))))
    print(markdown_table(rows, ["model", "n", "auc", "rmse"]))
    save_results("knowledge_tracing" + ("_synthetic" if args.synthetic else ""), {"results": rows})


if __name__ == "__main__":
    main()
