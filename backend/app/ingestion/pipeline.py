"""Ingestion pipeline: catalog + raw PDFs -> chunks -> Chroma + chunks.jsonl.

Incremental: a manifest stores each PDF's SHA-256. On re-run only new or modified documents are
re-processed (their old chunks are deleted first), and documents whose PDF disappeared are
removed from the index. Each document keeps a `version` counter.

Usage:
    python -m app.ingestion.pipeline            # from backend/
    python -m app.ingestion.pipeline --force    # rebuild everything
    python -m app.ingestion.pipeline --no-ocr
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from ..retrieval.embeddings import Embedder, get_embedder
from ..retrieval.store import ChunkRecords, VectorStore, chunk_metadata
from .chunker import chunk_document
from .pdf_loader import load_pdf
from ..study import load_uploads

log = logging.getLogger(__name__)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IngestionPipeline:
    def __init__(self, data_dir: Path, store: VectorStore, embedder: Embedder, use_ocr: bool = True,
                 pages_cache: Path | None = None):
        self.data_dir = data_dir
        self.raw_dir = data_dir / "raw"
        self.manifest_path = data_dir / "processed" / "manifest.json"
        self.store = store
        self.embedder = embedder
        self.records = ChunkRecords(data_dir / "processed" / "chunks.jsonl")
        self.use_ocr = use_ocr
        # per-page text/OCR cache, shared across DATA_DIRs (PAGES_CACHE_DIR) for ablations
        self.pages_cache = pages_cache or data_dir / "processed" / "pages"
        # official corpus catalog + PDFs uploaded by students (data/processed/uploads.json)
        catalog = json.loads((data_dir / "catalog.json").read_text("utf-8")) + load_uploads(data_dir)
        self.catalog = {d["doc_id"]: d for d in catalog}
        self.manifest: dict = (json.loads(self.manifest_path.read_text("utf-8"))
                               if self.manifest_path.exists() else {})

    def ingest_document(self, doc: dict, pdf: Path, digest: str) -> int:
        pages = load_pdf(pdf, use_ocr=self.use_ocr, cache_dir=self.pages_cache, digest=digest)
        chunks = chunk_document(doc["doc_id"], pages, doc.get("concepts"),
                                size=settings.chunk_size, overlap=settings.chunk_overlap)
        records = []
        for c in chunks:
            raw = asdict(c)
            raw["content_hash"] = hashlib.md5(c.text.encode()).hexdigest()
            records.append({"chunk_id": c.chunk_id, "doc_id": c.doc_id, "text": c.text,
                            "metadata": chunk_metadata(raw, doc)})
        self.store.delete_doc(doc["doc_id"])
        if records:
            texts = [r["text"] for r in records]
            # prepend title + section so the embedding knows the context of the chunk
            to_embed = [f"{doc['title']} | {r['metadata']['section']}\n{r['text']}" for r in records]
            self.store.upsert([r["chunk_id"] for r in records], texts,
                              self.embedder.embed_documents(to_embed), [r["metadata"] for r in records])
        self.records.replace_doc(doc["doc_id"], records)
        prev = self.manifest.get(doc["doc_id"], {})
        self.manifest[doc["doc_id"]] = {
            "sha256": digest,
            "version": prev.get("version", 0) + 1,
            "chunks": len(records),
            "pages": len(pages),
            "ocr_pages": sum(p.ocr for p in pages),
            "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return len(records)

    def save(self) -> None:
        self.records.save()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.manifest, indent=2), "utf-8")
        tmp.replace(self.manifest_path)

    def ingest_one(self, doc_id: str, force: bool = False) -> int:
        """Index a single catalog/uploaded document (used right after an upload)."""
        doc = self.catalog[doc_id]
        pdf = self.raw_dir / f"{doc_id}.pdf"
        digest = sha256(pdf)
        known = self.manifest.get(doc_id)
        if known and known["sha256"] == digest and not force:
            return known["chunks"]
        n = self.ingest_document(doc, pdf, digest)
        self.save()
        return n

    def run(self, force: bool = False) -> dict:
        stats = {"new": 0, "updated": 0, "unchanged": 0, "removed": 0, "missing_pdf": 0, "chunks": 0}
        for doc_id, doc in self.catalog.items():
            pdf = self.raw_dir / f"{doc_id}.pdf"
            if not pdf.exists():
                stats["missing_pdf"] += 1
                continue
            digest = sha256(pdf)
            known = self.manifest.get(doc_id)
            if known and known["sha256"] == digest and not force:
                stats["unchanged"] += 1
                continue
            try:
                n = self.ingest_document(doc, pdf, digest)
            except MemoryError:
                log.error("%s: out of memory, skipped (re-run to retry)", doc_id)
                stats["failed"] = stats.get("failed", 0) + 1
                continue
            stats["updated" if known else "new"] += 1
            stats["chunks"] += n
            log.info("%s: %d chunks", doc_id, n)
            self.save()  # checkpoint: a crash later does not lose finished documents
        # documents that were indexed but whose PDF is gone
        for doc_id in list(self.manifest):
            if not (self.raw_dir / f"{doc_id}.pdf").exists():
                self.store.delete_doc(doc_id)
                self.records.remove_doc(doc_id)
                del self.manifest[doc_id]
                stats["removed"] += 1
        self.save()
        stats["total_chunks"] = self.store.count()
        return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args()
    cache = os.getenv("PAGES_CACHE_DIR")
    pipe = IngestionPipeline(settings.data_dir, VectorStore(settings.chroma_dir),
                             get_embedder(settings.embedding_model), use_ocr=not args.no_ocr,
                             pages_cache=Path(cache) if cache else None)
    print(pipe.run(force=args.force))


if __name__ == "__main__":
    main()
