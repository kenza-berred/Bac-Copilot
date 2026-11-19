"""Chroma vector store + the chunk records it is built from.

Metadata stored per chunk (all scalars, as Chroma requires):
  doc_id, title, doc_type, year, session, page, section, points, has_correction, ocr,
  concepts (comma-joined) and one boolean flag per concept (`c_<concept>`) so we can filter
  by concept with a plain `where` clause.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb

from ..concepts import CONCEPTS

COLLECTION = "svt_chunks"


def chunk_metadata(chunk: dict, doc: dict) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "doc_id": doc["doc_id"],
        "title": doc["title"],
        "doc_type": doc["doc_type"],
        "year": doc.get("year") or 0,
        "session": doc.get("session") or "",
        "page": chunk["page"],
        "section": chunk.get("section") or "",
        "points": chunk.get("points") or 0.0,
        "has_correction": bool(doc.get("has_correction")),
        "ocr": bool(chunk.get("ocr")),
        "concepts": ",".join(chunk.get("concepts") or []),
        "pdf_url": doc.get("pdf_url", ""),
        "content_hash": chunk.get("content_hash", ""),
    }
    for cid in CONCEPTS:
        meta[f"c_{cid}"] = cid in (chunk.get("concepts") or [])
    return meta


class VectorStore:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        self.col = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    def upsert(self, ids: list[str], texts: list[str], embeddings: list[list[float]], metas: list[dict]):
        for i in range(0, len(ids), 500):
            self.col.upsert(ids=ids[i:i + 500], documents=texts[i:i + 500],
                            embeddings=embeddings[i:i + 500], metadatas=metas[i:i + 500])

    def delete_doc(self, doc_id: str) -> None:
        self.col.delete(where={"doc_id": doc_id})

    def count(self) -> int:
        return self.col.count()

    def query(self, embedding: list[float], k: int, where: dict | None = None) -> list[dict]:
        res = self.col.query(query_embeddings=[embedding], n_results=k, where=where or None)
        out = []
        for cid, text, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0],
                                         res["distances"][0]):
            out.append({"chunk_id": cid, "text": text, "metadata": meta, "score": 1 - dist})
        return out


class ChunkRecords:
    """chunks.jsonl — the source of truth for BM25, evaluation and the PDF viewer."""

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.records[r["chunk_id"]] = r

    def replace_doc(self, doc_id: str, chunks: list[dict]) -> None:
        self.records = {k: v for k, v in self.records.items() if v["doc_id"] != doc_id}
        for c in chunks:
            self.records[c["chunk_id"]] = c

    def remove_doc(self, doc_id: str) -> None:
        self.replace_doc(doc_id, [])

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for r in self.records.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def all(self) -> list[dict]:
        return list(self.records.values())
