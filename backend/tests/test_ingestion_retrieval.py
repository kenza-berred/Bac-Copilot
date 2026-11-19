from app.concepts import prerequisites_closure, tag_concepts
from app.ingestion.chunker import chunk_document
from app.ingestion.pdf_loader import PageText, load_pdf
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.hybrid import Filters, Retriever, rrf_fuse
from app.retrieval.store import ChunkRecords, VectorStore

from .conftest import make_pdf


def test_tag_concepts_on_accented_text():
    text = "Le crossing-over en prophase I de la méiose assure le brassage intrachromosomique."
    assert tag_concepts(text)[0] == "brassage"


def test_prerequisites_closure():
    assert prerequisites_closure("dihybridisme")[:2] == ["monohybridisme", "brassage"]
    assert "soi_non_soi" in prerequisites_closure("dysfonctionnement_immunitaire")


def test_chunks_keep_page_and_section():
    pages = [PageText(1, "Intro.\n" + "Texte du cours sur les neurones. " * 10),
             PageText(2, "Exercice 1 (3 points)\nLe potentiel d'action se propage le long de l'axone. " * 3)]
    chunks = chunk_document("d", pages, size=200, overlap=40)
    assert {c.page for c in chunks} == {1, 2}
    ex = [c for c in chunks if c.page == 2]
    assert ex[0].section.startswith("Exercice 1") and ex[0].points == 3.0
    assert all(len(c.text) <= 300 for c in chunks)


def test_load_pdf(data_dir):
    pages = load_pdf(data_dir / "raw" / "doc-1.pdf", use_ocr=False)
    assert len(pages) == 2 and "plasmocytes" in pages[0].text


def _pipeline(data_dir):
    return IngestionPipeline(data_dir, VectorStore(data_dir / "chroma"), HashingEmbedder(), use_ocr=False)


def test_incremental_ingestion(data_dir):
    stats = _pipeline(data_dir).run()
    assert stats["new"] == 2 and stats["total_chunks"] > 0
    assert _pipeline(data_dir).run()["unchanged"] == 2           # nothing changed
    make_pdf(data_dir / "raw" / "doc-2.pdf", ["Nouvelle version: le test-cross révèle les gènes liés."])
    pipe = _pipeline(data_dir)
    stats = pipe.run()
    assert stats["updated"] == 1 and pipe.manifest["doc-2"]["version"] == 2
    (data_dir / "raw" / "doc-1.pdf").unlink()
    stats = _pipeline(data_dir).run()
    assert stats["removed"] == 1
    records = ChunkRecords(data_dir / "processed" / "chunks.jsonl").all()
    assert {r["doc_id"] for r in records} == {"doc-2"}


def test_retrieval_modes_and_filters(data_dir):
    _pipeline(data_dir).run()
    r = Retriever(VectorStore(data_dir / "chroma"), ChunkRecords(data_dir / "processed" / "chunks.jsonl"),
                  HashingEmbedder(), reranker_name=None)
    for mode in ("dense", "bm25", "hybrid", "hybrid_rerank"):
        hits = r.search("Quel est le rôle des plasmocytes et des anticorps ?", k=3, mode=mode)
        assert hits and hits[0]["metadata"]["doc_id"] == "doc-1", mode
    hits = r.search("méiose crossing-over", k=5, mode="hybrid", filters=Filters(concept="brassage"))
    assert hits and all(h["metadata"]["c_brassage"] for h in hits)
    hits = r.search("anticorps", k=5, mode="hybrid", filters=Filters(doc_types=["resume"]))
    assert all(h["metadata"]["doc_type"] == "resume" for h in hits)


def test_rrf_prefers_consensus():
    a = [{"chunk_id": "x"}, {"chunk_id": "y"}]
    b = [{"chunk_id": "y"}, {"chunk_id": "z"}]
    assert rrf_fuse([a, b])[0]["chunk_id"] == "y"


def test_page_cache_reused(data_dir, monkeypatch):
    import app.ingestion.pdf_loader as pl
    cache = data_dir / "pages"
    pdf = data_dir / "raw" / "doc-1.pdf"
    first = load_pdf(pdf, use_ocr=False, cache_dir=cache, digest="abc")
    assert (cache / "doc-1.json").exists()
    monkeypatch.setattr(pl, "_extract_pages", lambda *a: (_ for _ in ()).throw(AssertionError("re-extracted")))
    assert load_pdf(pdf, use_ocr=False, cache_dir=cache, digest="abc") == first
