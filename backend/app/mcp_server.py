"""MCP server exposing the copilot's capabilities as tools.

Any MCP client (Claude Desktop, Cursor, the demo client in scripts/mcp_client_demo.py, or a
LangGraph agent through langchain-mcp-adapters) can search the SVT course, read a student's
mastery, generate a bac-style quiz and grade an answer.

Run (stdio):   cd backend && python -m app.mcp_server
Inspector:     cd backend && mcp dev app/mcp_server.py
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .concepts import CONCEPTS, graph_as_dict
from .retrieval.hybrid import Filters
from .services import get_agent, get_retriever, get_students

mcp = FastMCP("bac-copilot-svt")


@mcp.tool()
def search_course(query: str, concept: str | None = None, doc_types: list[str] | None = None,
                  year: int | None = None, k: int = 5) -> list[dict]:
    """Search the SVT course base (cours, résumés, séries, devoirs, bac sujets/corrigés 2008-2019).

    Args:
        query: question or keywords, in French ideally.
        concept: optional concept id to restrict the search (see get_concept_graph).
        doc_types: optional subset of cours, resume, serie, devoir, revision, bac_sujet, bac_corrige.
        year: optional bac year (2008-2019).
        k: number of passages to return.
    Returns passages with their source document, page and section, for citation.
    """
    hits = get_retriever().search(query, k=k, filters=Filters(doc_types=doc_types, concept=concept, year=year))
    return [{"rank": h["rank"], "text": h["text"], "title": h["metadata"]["title"],
             "doc_id": h["metadata"]["doc_id"], "page": h["metadata"]["page"],
             "section": h["metadata"]["section"], "concepts": h["metadata"]["concepts"]} for h in hits]


@mcp.tool()
def get_concept_graph() -> dict:
    """Return the SVT curriculum concept graph: chapters, concepts and prerequisite edges."""
    return graph_as_dict()


@mcp.tool()
def get_student_mastery(student_id: str) -> dict:
    """Return a student's estimated mastery (BKT probability) per concept and what to study next."""
    sm = get_students()
    return {"mastery": sm.mastery(student_id), "recommendations": sm.recommend(student_id, n=3)}


@mcp.tool()
def generate_quiz(student_id: str, n: int = 3, concepts: list[str] | None = None,
                  kinds: list[str] | None = None) -> dict:
    """Generate validated bac-style practice questions (qcm, short, analysis) with grading rubrics.

    If `concepts` is empty the student model picks the concepts the student most needs to practise.
    """
    bad = [c for c in concepts or [] if c not in CONCEPTS]
    if bad:
        return {"error": f"unknown concepts {bad}; call get_concept_graph"}
    out = get_agent().quiz(student_id, n=n, concepts=concepts, kinds=kinds)
    return {"concepts": out["quiz_params"]["concepts"], "questions": out["questions"],
            "rejected": out.get("rejected", [])}


@mcp.tool()
def grade_answer(student_id: str, question: str, student_answer: str, concept: str | None = None,
                 rubric: list[dict] | None = None, max_points: float = 2.0) -> dict:
    """Grade a student's answer like a bac examiner (criterion-by-criterion, partial credit),
    update the student's mastery and diagnose weak prerequisites."""
    out = get_agent().grade(student_id, question, student_answer, rubric=rubric, concept=concept,
                            max_points=max_points)
    return {"grade": out["grade"], "mastery_update": out.get("mastery_update"),
            "weak_prerequisites": out.get("diagnosis", [])}


@mcp.tool()
def schedule_review(student_id: str, n: int = 3) -> list[dict]:
    """Spaced-repetition plan: the concepts to review next, with the reason (due review, weak, new)."""
    return [{"concept": r["concept"], "label": r["label"], "reason": r["reason"], "p_know": r["p_know"],
             "next_review": r["next_review"]} for r in get_students().recommend(student_id, n=n)]


if __name__ == "__main__":
    mcp.run()
