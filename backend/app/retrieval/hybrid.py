"""Retriever with four modes, so the benchmark can compare them:

    dense          — E5 embeddings + Chroma
    bm25           — keyword search
    hybrid         — dense + BM25 fused with Reciprocal Rank Fusion (RRF)
    hybrid_rerank  — hybrid candidates re-scored by a multilingual cross-encoder

Filters (doc_type, concept, year, has_correction) are applied in both indexes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from ..config import settings
from .bm25 import BM25Index
from .embeddings import Embedder, get_embedder
from .store import ChunkRecords, VectorStore

log = logging.getLogger(__name__)
MODES = ("dense", "bm25", "hybrid", "hybrid_rerank")


@dataclass
class Filters:
    doc_types: list[str] | None = None
    concept: str | None = None
    year: int | None = None
    has_correction: bool | None = None

    def to_where(self) -> dict | None:
        clauses = []
        if self.doc_types:
            clauses.append({"doc_type": {"$in": self.doc_types}})
        if self.concept:
            clauses.append({f"c_{self.concept}": True})
        if self.year:
            clauses.append({"year": self.year})
        if self.has_correction is not None:
            clauses.append({"has_correction": self.has_correction})
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def match(self, record: dict) -> bool:
        m = record["metadata"]
        if self.doc_types and m["doc_type"] not in self.doc_types:
            return False
        if self.concept and not m.get(f"c_{self.concept}"):
            return False
        if self.year and m.get("year") != self.year:
            return False
        if self.has_correction is not None and m.get("has_correction") != self.has_correction:
            return False
        return True


def rrf_fuse(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: score = sum 1/(k + rank). Robust to incomparable score scales."""
    fused: dict[str, dict] = {}
    for results in result_lists:
        for rank, r in enumerate(results, 1):
            entry = fused.setdefault(r["chunk_id"], {**r, "score": 0.0})
            entry["score"] += 1.0 / (k + rank)
    return sorted(fused.values(), key=lambda r: r["score"], reverse=True)


@lru_cache(maxsize=1)
def _cross_encoder(name: str):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(name)


class Retriever:
    def __init__(self, store: VectorStore, records: ChunkRecords, embedder: Embedder,
                 reranker_name: str | None = None):
        self.store = store
        self.records = records
        self.embedder = embedder
        self.bm25 = BM25Index(records.all())
        self.reranker_name = reranker_name

    @classmethod
    def from_settings(cls) -> "Retriever":
        return cls(
            VectorStore(settings.chroma_dir),
            ChunkRecords(settings.processed_dir / "chunks.jsonl"),
            get_embedder(settings.embedding_model),
            settings.reranker_model or None,
        )

    def refresh(self) -> None:
        """Reload records after ingestion (keeps BM25 in sync with Chroma)."""
        self.records = ChunkRecords(self.records.path)
        self.bm25 = BM25Index(self.records.all())

    def rerank(self, query: str, candidates: list[dict], k: int) -> list[dict]:
        if not candidates or not self.reranker_name:
            return candidates[:k]
        model = _cross_encoder(self.reranker_name)
        scores = model.predict([(query, c["text"]) for c in candidates])
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        return sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)[:k]

    def search(self, query: str, k: int | None = None, mode: str = "hybrid_rerank",
               filters: Filters | None = None) -> list[dict]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        k = k or settings.top_k
        filters = filters or Filters()
        n = max(settings.candidate_k, k)

        dense = bm25 = []
        if mode != "bm25":
            dense = self.store.query(self.embedder.embed_query(query), n, filters.to_where())
        if mode != "dense":
            bm25 = self.bm25.search(query, n, filters.match)

        if mode == "dense":
            results = dense[:k]
        elif mode == "bm25":
            results = bm25[:k]
        elif mode == "hybrid":
            results = rrf_fuse([dense, bm25])[:k]
        else:
            results = self.rerank(query, rrf_fuse([dense, bm25]), k)
        for rank, r in enumerate(results, 1):
            r["rank"] = rank
        return results
