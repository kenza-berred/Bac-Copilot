"""Retrieval and grading metrics."""
from __future__ import annotations

import math

import numpy as np


def is_relevant(hit_meta: dict, relevant: list[dict]) -> bool:
    """A retrieved chunk is relevant if it comes from an annotated (doc_id, page).
    `page: null` in the annotation means "any page of this document"."""
    for r in relevant:
        if hit_meta["doc_id"] == r["doc_id"] and (r.get("page") in (None, hit_meta["page"])):
            return True
    return False


def first_relevant_rank(hits: list[dict], relevant: list[dict]) -> int | None:
    for i, h in enumerate(hits, 1):
        if is_relevant(h["metadata"], relevant):
            return i
    return None


def recall_at_k(hits: list[dict], relevant: list[dict], k: int) -> float:
    """Fraction of annotated relevant passages found in the top-k (distinct doc/page pairs)."""
    if not relevant:
        return 0.0
    found = {(r["doc_id"], r.get("page")) for r in relevant
             if any(is_relevant(h["metadata"], [r]) for h in hits[:k])}
    return len(found) / len(relevant)


def hit_at_k(hits: list[dict], relevant: list[dict], k: int) -> float:
    rank = first_relevant_rank(hits, relevant)
    return float(rank is not None and rank <= k)


def reciprocal_rank(hits: list[dict], relevant: list[dict]) -> float:
    rank = first_relevant_rank(hits, relevant)
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(hits: list[dict], relevant: list[dict], k: int) -> float:
    gains = [1.0 if is_relevant(h["metadata"], relevant) else 0.0 for h in hits[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def quadratic_weighted_kappa(a: list[int], b: list[int]) -> float:
    a, b = np.asarray(a), np.asarray(b)
    lo, hi = min(a.min(), b.min()), max(a.max(), b.max())
    n = hi - lo + 1
    if n <= 1:
        return 1.0
    O = np.zeros((n, n))
    for x, y in zip(a - lo, b - lo):
        O[x, y] += 1
    W = np.array([[(i - j) ** 2 / (n - 1) ** 2 for j in range(n)] for i in range(n)])
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    return 1 - (W * O).sum() / (W * E).sum() if (W * E).sum() else 1.0


def grading_agreement(pred: list[float], gold: list[float], max_scores: list[float]) -> dict:
    p, g, m = np.asarray(pred), np.asarray(gold), np.asarray(max_scores)
    pn, gn = p / m, g / m
    # QWK on half-point bands of the normalized score (0, .1, ..., 1 -> 0..10)
    qwk = quadratic_weighted_kappa(list(np.rint(pn * 10).astype(int)), list(np.rint(gn * 10).astype(int)))
    return {
        "n": int(len(p)),
        "mae_points": float(np.mean(np.abs(p - g))),
        "mae_normalized": float(np.mean(np.abs(pn - gn))),
        "within_0.5pt": float(np.mean(np.abs(p - g) <= 0.5)),
        "pearson": float(np.corrcoef(pn, gn)[0, 1]) if len(p) > 2 and pn.std() and gn.std() else float("nan"),
        "qwk": float(qwk),
        "bias_points": float(np.mean(p - g)),  # >0: the model is more lenient than the human
    }
