"""REST API used by the web interface.

Run:  cd backend && uvicorn app.api:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import re
import threading

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .concepts import CONCEPTS, graph_as_dict
from .config import settings
from .services import get_agent, get_retriever, get_students
from . import study

log = logging.getLogger(__name__)
_ingest_lock = threading.Lock()  # one ingestion at a time (Chroma + chunks.jsonl writers)

app = FastAPI(title="Bac Copilot SVT", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


class ChatIn(BaseModel):
    student_id: str = "demo"
    message: str
    history: list[dict] = Field(default_factory=list)


class QuizIn(BaseModel):
    student_id: str = "demo"
    n: int = Field(3, ge=1, le=8)
    concepts: list[str] = Field(default_factory=list)
    kinds: list[str] | None = None
    difficulty: str = "bac"


class GradeIn(BaseModel):
    student_id: str = "demo"
    question: str
    student_answer: str
    rubric: list[dict] | None = None
    reference: str | None = None
    concept: str | None = None
    max_points: float = 2.0


@app.get("/api/health")
def health():
    return {"status": "ok", "chunks": get_retriever().store.count()}


@app.get("/api/concepts")
def concepts():
    return graph_as_dict()


@app.post("/api/chat")
def chat(body: ChatIn):
    out = get_agent().chat(body.student_id, body.message, body.history)
    if out["intent"] == "quiz":  # "donne-moi un exercice" typed in the chat
        out = get_agent().quiz(body.student_id, concepts=[out["concept"]] if out.get("concept") else None)
        return {"intent": "quiz", "questions": out["questions"], "trace": out["trace"]}
    return {"intent": out["intent"], "answer": out.get("answer", ""), "citations": out.get("citations", []),
            "verified": out.get("verified", True), "recommendations": out.get("recommendations", []),
            "trace": out["trace"]}


@app.post("/api/quiz")
def quiz(body: QuizIn):
    unknown = [c for c in body.concepts if c not in CONCEPTS]
    if unknown:
        raise HTTPException(400, f"unknown concepts: {unknown}")
    out = get_agent().quiz(body.student_id, n=body.n, concepts=body.concepts, kinds=body.kinds,
                           difficulty=body.difficulty)
    return {"concepts": out["quiz_params"]["concepts"], "questions": out["questions"],
            "rejected": out.get("rejected", []), "trace": out["trace"]}


@app.post("/api/grade")
def grade(body: GradeIn):
    out = get_agent().grade(body.student_id, body.question, body.student_answer, rubric=body.rubric,
                            reference=body.reference, concept=body.concept, max_points=body.max_points)
    return {"grade": out["grade"], "mastery_update": out.get("mastery_update"),
            "diagnosis": out.get("diagnosis", []), "recommendations": out.get("recommendations", []),
            "trace": out["trace"]}


@app.get("/api/students/{student_id}")
def student(student_id: str):
    sm = get_students()
    sm.ensure_student(student_id)
    return {"mastery": sm.mastery(student_id), "recommendations": sm.recommend(student_id, n=3),
            "history": sm.history(student_id)}


@app.get("/api/documents")
def documents():
    catalog = json.loads(settings.catalog_path.read_text("utf-8")) + study.load_uploads(settings.data_dir)
    manifest_path = settings.processed_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    return [{**d, "indexed": d["doc_id"] in manifest, **({"version": manifest[d["doc_id"]]["version"],
                                                           "chunks": manifest[d["doc_id"]]["chunks"]}
                                                          if d["doc_id"] in manifest else {})}
            for d in catalog]


# ---------------------------------------------------------------- uploaded PDFs -> flashcards + quiz
class StudyIn(BaseModel):
    n_cards: int = Field(10, ge=1, le=20)
    n_questions: int = Field(5, ge=1, le=8)


def _build_study_pack(doc_id: str, n_cards: int = 10, n_questions: int = 5) -> None:
    """Background job: index the PDF, then generate its flashcards and quiz."""
    from .ingestion.pipeline import IngestionPipeline
    from .llm import get_llm

    data = settings.data_dir
    try:
        study.set_status(data, doc_id, "processing", "indexation (texte + OCR)")
        r = get_retriever()
        with _ingest_lock:
            IngestionPipeline(data, r.store, r.embedder).ingest_one(doc_id)
            r.refresh()
        study.set_status(data, doc_id, "processing", "génération des fiches et du quiz")
        doc = next(d for d in study.load_uploads(data) + json.loads(settings.catalog_path.read_text("utf-8"))
                   if d["doc_id"] == doc_id)
        records = [x for x in r.records.all() if x["doc_id"] == doc_id]
        pack = study.StudyPackBuilder(get_llm(), get_llm(fast=True)).build(
            doc, records, n_cards=n_cards, n_questions=n_questions)
        study.save_pack(data, doc_id, pack)
    except Exception as e:  # surfaced to the UI through the pack status
        log.exception("study pack failed for %s", doc_id)
        study.set_status(data, doc_id, "error", error=str(e)[:500])


@app.post("/api/documents/upload")
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...),
                          title: str | None = Form(None)):
    content = await file.read()
    try:
        doc = study.register_upload(settings.data_dir, file.filename or "document.pdf", content, title)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pack = study.load_pack(settings.data_dir, doc["doc_id"])
    if not pack or pack.get("status") == "error":
        study.set_status(settings.data_dir, doc["doc_id"], "processing", "en file d'attente")
        background.add_task(_build_study_pack, doc["doc_id"])
    return {**doc, "study": study.load_pack(settings.data_dir, doc["doc_id"])}


@app.get("/api/documents/{doc_id}/study")
def get_study_pack(doc_id: str):
    try:
        pack = study.load_pack(settings.data_dir, doc_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not pack:
        raise HTTPException(404, "no study pack for this document")
    return pack


@app.post("/api/documents/{doc_id}/study")
def regenerate_study_pack(doc_id: str, background: BackgroundTasks, body: StudyIn | None = None):
    """(Re)generate flashcards + quiz for any downloaded document (uploaded or from the corpus)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", doc_id) or not (settings.raw_dir / f"{doc_id}.pdf").exists():
        raise HTTPException(404, "document not downloaded")
    body = body or StudyIn()
    study.set_status(settings.data_dir, doc_id, "processing", "en file d'attente")
    background.add_task(_build_study_pack, doc_id, body.n_cards, body.n_questions)
    return study.load_pack(settings.data_dir, doc_id)


@app.get("/api/documents/{doc_id}/pdf")
def document_pdf(doc_id: str):
    path = (settings.raw_dir / f"{doc_id}.pdf").resolve()
    if path.parent != settings.raw_dir.resolve() or not path.exists():
        raise HTTPException(404, "document not downloaded")
    return FileResponse(path, media_type="application/pdf")


@app.post("/api/ingest")
def ingest(force: bool = False):
    from .ingestion.pipeline import IngestionPipeline

    r = get_retriever()
    with _ingest_lock:
        stats = IngestionPipeline(settings.data_dir, r.store, r.embedder).run(force=force)
        r.refresh()
    return stats
