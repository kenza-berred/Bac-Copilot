"""Study packs for PDFs uploaded by the student: flashcards + a validated quiz built from the document.

Flow (triggered by POST /api/documents/upload):
    register_upload  -> data/raw/<up-xxxx>.pdf + data/processed/uploads.json (user catalog)
    ingest           -> same pipeline as the corpus (text layer, OCR fallback, chunks, embeddings)
    StudyPackBuilder -> flashcards (grounded on the document's chunks) + quiz (generate -> validate)
    save_pack        -> data/processed/study/<doc_id>.json, with a status the UI polls

Everything is generated from the uploaded document only: each card and question cites the
excerpts it comes from, and quiz questions go through the same LLM validation step as the agent's
mock exams (unverifiable questions are rejected).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .agent import prompts as P
from .agent.graph import CONCEPT_LIST, MAX_RETRIES, citation, format_context
from .agent.schemas import FlashcardsOut, QuizOut, Verdicts
from .concepts import CONCEPTS
from .llm import invoke_json

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 40 * 1024 * 1024
CONTEXT_CHUNKS = 10   # excerpts sent to the LLM (keeps each call under Groq free-tier token limits)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------- uploads catalog
def uploads_path(data_dir: Path) -> Path:
    return data_dir / "processed" / "uploads.json"


def load_uploads(data_dir: Path) -> list[dict]:
    p = uploads_path(data_dir)
    return json.loads(p.read_text("utf-8")) if p.exists() else []


def register_upload(data_dir: Path, filename: str, content: bytes, title: str | None = None) -> dict:
    """Validate and store an uploaded PDF. Re-uploading the same file returns the existing entry."""
    if not content.lstrip()[:5] == b"%PDF-":
        raise ValueError("Seuls les fichiers PDF sont acceptés.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES // 2**20} Mo).")
    doc_id = "up-" + hashlib.sha256(content).hexdigest()[:10]
    raw = data_dir / "raw" / f"{doc_id}.pdf"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(content)
    uploads = load_uploads(data_dir)
    for d in uploads:
        if d["doc_id"] == doc_id:
            return d
    name = Path(filename or "document.pdf").stem.replace("_", " ").replace("-", " ").strip()
    doc = {"doc_id": doc_id, "title": (title or name or "Mon document")[:120], "doc_type": "upload",
           "has_correction": False, "concepts": None, "year": None, "session": None,
           "page_url": "", "pdf_url": "", "source": "upload", "uploaded_at": _now()}
    _write_json(uploads_path(data_dir), uploads + [doc])
    return doc


# ---------------------------------------------------------------------------- pack storage
def pack_path(data_dir: Path, doc_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", doc_id):
        raise ValueError(f"invalid doc_id {doc_id!r}")
    return data_dir / "processed" / "study" / f"{doc_id}.json"


def load_pack(data_dir: Path, doc_id: str) -> dict | None:
    p = pack_path(data_dir, doc_id)
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def save_pack(data_dir: Path, doc_id: str, pack: dict) -> None:
    _write_json(pack_path(data_dir, doc_id), pack)


def set_status(data_dir: Path, doc_id: str, status: str, stage: str = "", error: str = "") -> None:
    pack = load_pack(data_dir, doc_id) or {"doc_id": doc_id}
    pack.update({"status": status, "stage": stage, "error": error, "updated_at": _now()})
    save_pack(data_dir, doc_id, pack)


# ---------------------------------------------------------------------------- generation
def _chunk_order(r: dict) -> tuple[int, int]:
    try:
        return r["metadata"]["page"], int(r["chunk_id"].rsplit(":c", 1)[1])
    except (IndexError, ValueError):
        return r["metadata"]["page"], 0


def select_chunks(records: list[dict], limit: int = CONTEXT_CHUNKS) -> list[dict]:
    """Evenly spread excerpts over the whole document (in reading order)."""
    records = sorted(records, key=_chunk_order)
    if len(records) <= limit:
        return records
    step = len(records) / limit
    return [records[int(i * step)] for i in range(limit)]


def main_concepts(records: list[dict], n: int = 3) -> list[str]:
    counts = Counter(c for r in records for c in (r["metadata"].get("concepts") or "").split(",") if c)
    return [c for c, _ in counts.most_common(n) if c in CONCEPTS]


class StudyPackBuilder:
    def __init__(self, llm: BaseChatModel, fast: BaseChatModel):
        self.llm = llm
        self.fast = fast

    def flashcards(self, title: str, docs: list[dict], n: int, fallback_concept: str | None) -> list[dict]:
        out = invoke_json(self.llm, P.FLASHCARDS_SYSTEM.format(concepts=CONCEPT_LIST),
                          P.FLASHCARDS_USER.format(n=n, title=title, context=format_context(docs)),
                          FlashcardsOut)
        cards, seen = [], set()
        for c in out.cards:
            key = c.front.strip().lower()
            srcs = [citation(i, docs[i - 1]) for i in c.source_ids if 1 <= i <= len(docs)]
            if not srcs or key in seen or not c.back.strip():   # ungrounded or duplicate card
                continue
            seen.add(key)
            cards.append({"id": f"f{len(cards) + 1}", "front": c.front.strip(), "back": c.back.strip(),
                          "concept": c.concept or fallback_concept, "sources": srcs})
        return cards[:n]

    def quiz(self, title: str, docs: list[dict], n: int, kinds: list[str], difficulty: str,
             fallback_concept: str | None) -> tuple[list[dict], list[dict]]:
        context = format_context(docs)
        kept: list[dict] = []
        rejected: list[dict] = []
        for _ in range(MAX_RETRIES + 1):
            missing = n - len(kept)
            if missing <= 0:
                break
            drafts = invoke_json(self.llm, P.QUIZ_SYSTEM.format(concepts=CONCEPT_LIST),
                                 P.QUIZ_DOC_USER.format(n=missing, title=title, kinds=", ".join(kinds),
                                                        difficulty=difficulty, context=context),
                                 QuizOut).questions[:missing]
            listing = "\n".join(f"#{i}: {q.question} | options={q.options} | réponse modèle: {q.answer} "
                                f"| sources={q.source_ids}" for i, q in enumerate(drafts))
            verdicts = invoke_json(self.fast, P.VALIDATE_SYSTEM,
                                   P.VALIDATE_USER.format(context=context, questions=listing), Verdicts)
            valid = {v.index for v in verdicts.verdicts if v.valid}
            reasons = {v.index: v.reason for v in verdicts.verdicts}
            for i, q in enumerate(drafts):
                srcs = [citation(j, docs[j - 1]) for j in q.source_ids if 1 <= j <= len(docs)]
                if any(k["question"].strip().lower() == q.question.strip().lower() for k in kept):
                    continue  # same question proposed again on retry
                if i in valid and srcs:
                    kept.append({**q.model_dump(), "validated": True, "sources": srcs})
                else:
                    rejected.append({"question": q.question,
                                     "reason": reasons.get(i) or "sources invalides"})
        questions = [{**q, "id": f"q{i + 1}", "concept": q.get("concept") or fallback_concept,
                      "max_points": sum(r["points"] for r in q["rubric"]) or 1.0}
                     for i, q in enumerate(kept[:n])]
        return questions, rejected

    def build(self, doc: dict, records: list[dict], n_cards: int = 10, n_questions: int = 5,
              kinds: list[str] | None = None, difficulty: str = "bac") -> dict:
        if not records:
            raise ValueError("Aucun texte exploitable dans ce PDF (page blanche ou scan illisible).")
        docs = select_chunks(records)
        concepts = main_concepts(records)
        fallback = concepts[0] if concepts else None
        cards = self.flashcards(doc["title"], docs, n_cards, fallback)
        questions, rejected = self.quiz(doc["title"], docs, n_questions, kinds or ["qcm", "short", "analysis"],
                                        difficulty, fallback)
        return {"doc_id": doc["doc_id"], "title": doc["title"], "status": "ready", "stage": "", "error": "",
                "generated_at": _now(), "concepts": concepts, "n_chunks": len(records),
                "flashcards": cards, "questions": questions, "rejected": rejected}
