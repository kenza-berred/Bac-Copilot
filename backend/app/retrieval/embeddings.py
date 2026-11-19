"""Embedding models.

`E5Embedder` wraps a multilingual E5 model (French course content, French/Arabic questions).
E5 expects "query: " / "passage: " prefixes — forgetting them costs several points of recall.

`HashingEmbedder` is a dependency-free fallback used in unit tests and CI.
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Protocol

import numpy as np



class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class E5Embedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode([f"passage: {t}" for t in texts], batch_size=32,
                                 normalize_embeddings=True, show_progress_bar=len(texts) > 200)
        return vecs.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(f"query: {text}", normalize_embeddings=True).tolist()


class HashingEmbedder:
    """Bag-of-words hashing trick. Not semantic — only for tests."""

    def __init__(self, dim: int = 256):
        self.name = f"hashing-{dim}"
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = np.zeros(self.dim)
        from .bm25 import tokenize

        for tok in tokenize(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@lru_cache(maxsize=2)
def get_embedder(model_name: str) -> Embedder:
    if model_name.startswith("hashing"):
        return HashingEmbedder()
    return E5Embedder(model_name)
