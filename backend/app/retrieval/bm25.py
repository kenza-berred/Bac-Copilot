"""BM25 keyword index with French-aware tokenization.

Dense retrieval misses exact technical terms ("LT8", "crossing-over", "PPSE"); BM25 catches them.
"""
from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from ..concepts import normalize

FR_STOPWORDS = set("""
a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me meme mes
moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un
une vos votre vous c d j l m n s t y ete etre est sont a ont cette cet celle celui ceux comme
plus tres tout tous toute toutes donc car si alors entre chez sans sous vers lors ainsi aussi
""".split())


def light_stem(tok: str) -> str:
    """Very light French stemming: plural and common suffixes (keeps tokens readable)."""
    for suf in ("ements", "ement", "ations", "ation", "iques", "ique", "eurs", "eur", "es", "s", "e"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            return tok[: -len(suf)]
    return tok


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", normalize(text))
    return [light_stem(t) for t in toks if t not in FR_STOPWORDS and (len(t) > 1 or t.isdigit())]


class BM25Index:
    def __init__(self, records: list[dict]):
        self.records = records
        self.bm25 = BM25Okapi([tokenize(r["text"]) for r in records]) if records else None

    def search(self, query: str, k: int, predicate=None) -> list[dict]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            r = self.records[i]
            if predicate and not predicate(r):
                continue
            out.append({"chunk_id": r["chunk_id"], "text": r["text"], "metadata": r["metadata"],
                        "score": float(scores[i])})
            if len(out) >= k:
                break
        return out
