"""Uploaded PDF -> ingestion -> flashcards + validated quiz (offline, scripted LLM)."""
import pytest
from fastapi.testclient import TestClient

from app import study
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.store import VectorStore

from .conftest import COURSE_PAGES, make_pdf
from .fake_llm import ScriptedLLM

LLM = ScriptedLLM(responses={
    "fiches de révision": {"cards": [
        {"front": "Que sécrètent les plasmocytes ?", "back": "Des anticorps.", "concept": "reponse_specifique",
         "source_ids": [1]},
        {"front": "Que sécrètent les plasmocytes ?", "back": "doublon", "source_ids": [1]},   # duplicate
        {"front": "Carte inventée ?", "back": "x", "source_ids": [42]}]},                     # ungrounded
    "concepteur de sujets": {"questions": [
        {"question": "Quel est le rôle des LT8 ?", "type": "short", "options": [], "answer": "Lyse des cellules infectées.",
         "rubric": [{"criterion": "lyse", "points": 1}, {"criterion": "cellules infectées", "points": 1}],
         "concept": None, "source_ids": [2]},
        {"question": "Hors document ?", "type": "short", "options": [], "answer": "?",
         "rubric": [{"criterion": "x", "points": 1}], "source_ids": [1]}]},
    "contrôles la qualité": {"verdicts": [{"index": 0, "valid": True}, {"index": 1, "valid": False,
                                                                       "reason": "non vérifiable"}]},
})


def _pdf_bytes(tmp_path, pages):
    p = tmp_path / "upload.pdf"
    make_pdf(p, pages)
    return p.read_bytes()


def test_register_upload_rejects_non_pdf(data_dir):
    with pytest.raises(ValueError):
        study.register_upload(data_dir, "photo.png", b"\x89PNG....")
    with pytest.raises(ValueError):
        study.pack_path(data_dir, "../secret")


def test_upload_ingest_and_study_pack(data_dir, tmp_path):
    content = _pdf_bytes(tmp_path, COURSE_PAGES)
    doc = study.register_upload(data_dir, "Mon_cours_immunite.pdf", content)
    assert doc["doc_id"].startswith("up-") and doc["title"] == "Mon cours immunite"
    again = study.register_upload(data_dir, "copie.pdf", content)
    assert again["doc_id"] == doc["doc_id"] and len(study.load_uploads(data_dir)) == 1   # idempotent

    pipe = IngestionPipeline(data_dir, VectorStore(data_dir / "chroma"), HashingEmbedder(), use_ocr=False)
    assert pipe.ingest_one(doc["doc_id"]) > 0
    records = [r for r in pipe.records.all() if r["doc_id"] == doc["doc_id"]]

    pack = study.StudyPackBuilder(LLM, LLM).build(doc, records, n_cards=5, n_questions=2)
    assert pack["status"] == "ready"
    assert [c["front"] for c in pack["flashcards"]] == ["Que sécrètent les plasmocytes ?"]
    assert pack["flashcards"][0]["sources"][0]["doc_id"] == doc["doc_id"]
    assert len(pack["questions"]) == 1 and pack["questions"][0]["max_points"] == 2
    assert pack["questions"][0]["concept"] == pack["concepts"][0]      # falls back to the doc's main concept
    assert any(r["reason"] == "non vérifiable" for r in pack["rejected"])


def test_upload_endpoint(data_dir, tmp_path, monkeypatch):
    from dataclasses import replace

    from app import api
    monkeypatch.setattr(api, "settings", replace(api.settings, data_dir=data_dir))
    calls = []
    monkeypatch.setattr(api, "_build_study_pack", lambda doc_id, *a: calls.append(doc_id))
    client = TestClient(api.app)
    r = client.post("/api/documents/upload", files={"file": ("x.png", b"not a pdf", "image/png")})
    assert r.status_code == 400
    r = client.post("/api/documents/upload",
                    files={"file": ("cours.pdf", _pdf_bytes(tmp_path, COURSE_PAGES), "application/pdf")})
    assert r.status_code == 200 and r.json()["study"]["status"] == "processing"
    assert calls == [r.json()["doc_id"]]
    assert client.get(f"/api/documents/{r.json()['doc_id']}/study").json()["status"] == "processing"
