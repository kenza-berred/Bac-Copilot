import pytest

from app.agent.graph import CopilotAgent
from app.ingestion.pipeline import IngestionPipeline
from app.llm import extract_json
from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.hybrid import Retriever
from app.retrieval.store import ChunkRecords, VectorStore
from app.student.model import StudentModel, bkt_update, p_correct, sm2_next

from .fake_llm import ScriptedLLM


# ---------------------------------------------------------------- student model
def test_bkt_moves_in_the_right_direction():
    assert bkt_update(0.3, 1.0) > 0.3
    assert bkt_update(0.7, 0.0) < 0.7
    assert bkt_update(0.5, 0.5) > bkt_update(0.5, 0.0)
    assert 0 < p_correct(0.5) < 1


def test_sm2_intervals_grow_on_success_and_reset_on_failure():
    i, e = sm2_next(0, 2.5, 1.0)
    i2, e2 = sm2_next(i, e, 1.0)
    i3, _ = sm2_next(i2, e2, 1.0)
    assert i < i2 < i3
    assert sm2_next(i3, e2, 0.2)[0] == 1.0


def test_diagnosis_and_recommendation_prefer_weak_prerequisites(tmp_path):
    sm = StudentModel(tmp_path / "s.sqlite")
    for _ in range(3):
        sm.record_attempt("amine", "brassage", 0, 4)          # prerequisite failed
        sm.record_attempt("amine", "monohybridisme", 1, 4)
    gaps = [g["concept"] for g in sm.diagnose("amine", "dihybridisme")]
    assert gaps[:2] == ["monohybridisme", "brassage"]
    recs = [r["concept"] for r in sm.recommend("amine", n=2, chapter="genetique")]
    assert recs[0] == "brassage"
    status = {m["concept"]: m["status"] for m in sm.mastery("amine")}
    assert status["brassage"] == "à revoir" and status["procreation"] == "non évalué"


def test_extract_json_handles_fences():
    assert extract_json('Voici:\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}


# ---------------------------------------------------------------- agent (offline, scripted LLM)
@pytest.fixture
def agent(data_dir, tmp_path):
    IngestionPipeline(data_dir, VectorStore(data_dir / "chroma"), HashingEmbedder(), use_ocr=False).run()
    retriever = Retriever(VectorStore(data_dir / "chroma"), ChunkRecords(data_dir / "processed" / "chunks.jsonl"),
                          HashingEmbedder(), reranker_name=None)
    llm = ScriptedLLM(responses={
        "routeur": {"intent": "ask", "language": "fr", "search_query": "rôle des plasmocytes anticorps",
                    "concept": "reponse_specifique"},
        "Réponds UNIQUEMENT à partir des extraits": "Les plasmocytes sécrètent des anticorps [1].",
        "Tu vérifies une réponse": {"supported": True, "unsupported_claims": [], "better_query": None},
        "concepteur de sujets": {"questions": [
            {"question": "Quel est le rôle des plasmocytes ?", "type": "short", "options": [],
             "answer": "Ils sécrètent des anticorps.", "rubric": [{"criterion": "sécrétion d'anticorps", "points": 1}],
             "concept": "reponse_specifique", "difficulty": "facile", "source_ids": [1]},
            {"question": "Question invérifiable ?", "type": "short", "options": [], "answer": "?",
             "rubric": [{"criterion": "x", "points": 1}], "concept": "reponse_specifique", "source_ids": [9]}]},
        "contrôles la qualité": {"verdicts": [{"index": 0, "valid": True}, {"index": 1, "valid": False,
                                                                          "reason": "hors sources"}]},
        "Corrige la réponse": {"criteria": [{"criterion": "sécrétion d'anticorps", "max_points": 1,
                                             "awarded": 3, "comment": "ok"},
                                            {"criterion": "origine LB", "max_points": 1, "awarded": 0}],
                               "score": 99, "max_score": 2, "feedback": "Bien, voir [1].",
                               "misconceptions": [], "concept": "reponse_specifique"},
    })
    return CopilotAgent(retriever, StudentModel(tmp_path / "students.sqlite"), llm, retrieval_mode="hybrid")


def test_agent_answers_with_citations(agent):
    out = agent.chat("amine", "C'est quoi le rôle des plasmocytes ?")
    assert out["intent"] == "ask" and out["verified"]
    assert out["citations"] and out["citations"][0]["doc_id"] == "doc-1"
    assert out["citations"][0]["page"] >= 1


def test_agent_quiz_rejects_unverifiable_questions(agent):
    out = agent.quiz("amine", n=1, concepts=["reponse_specifique"])
    assert len(out["questions"]) == 1
    q = out["questions"][0]
    assert q["validated"] and q["sources"] and q["max_points"] == 1


def test_agent_grades_and_updates_mastery(agent):
    out = agent.grade("amine", "Quel est le rôle des plasmocytes ?", "Ils fabriquent des anticorps",
                      rubric=[{"criterion": "sécrétion d'anticorps", "points": 1}, {"criterion": "origine LB", "points": 1}],
                      concept="reponse_specifique")
    g = out["grade"]
    assert g["score"] == 1.0 and g["max_score"] == 2.0      # awarded clamped, totals recomputed
    assert out["mastery_update"]["concept"] == "reponse_specifique"
    assert [d["concept"] for d in out["diagnosis"]] == ["reponse_non_specifique", "soi_non_soi"]
