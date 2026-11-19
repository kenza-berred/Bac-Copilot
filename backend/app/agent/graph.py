"""The LangGraph agent.

                         ┌──────────► retrieve ─► answer ─► verify ──(unsupported, retry)──┐
                         │  ask          ▲                     │                          │
                         │               └─────────────────────┼──────────────────────────┘
    START ─► router ─────┤                                     └─► finalize_answer ─► END
                         │  quiz
                         ├──────────► plan_quiz ─► generate_questions ─► validate_questions ─┬─► finalize_quiz ─► END
                         │                               ▲                                    │
                         │                               └──────(too many rejected, retry)────┘
                         │  grade
                         ├──────────► prepare_grading ─► grade_answer ─► update_student ─► END
                         │  progress
                         └──────────► progress ─► END

Self-checks:
  * answers: every claim must cite an excerpt; an LLM verifier flags unsupported claims and can
    propose a better search query (one retry), otherwise the answer is flagged as uncertain;
  * generated questions: a verifier rejects questions that cannot be answered from their sources.
"""
from __future__ import annotations

import operator
import re
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph

from ..concepts import CONCEPTS
from ..retrieval.hybrid import Filters, Retriever
from ..student.model import StudentModel
from . import prompts as P
from .schemas import (GradeOut, QuizOut, RouteDecision, RubricOut, Verdicts, VerifyResult)
from ..llm import invoke_json, invoke_text

MAX_RETRIES = 1
CONCEPT_LIST = ", ".join(f"{c.id} ({c.label})" for c in CONCEPTS.values())


class AgentState(TypedDict, total=False):
    student_id: str
    message: str
    history: list[dict]
    intent: str
    language: str
    search_query: str
    concept: str | None
    docs: list[dict]
    answer: str
    citations: list[dict]
    verified: bool
    unsupported: list[str]
    attempts: int
    quiz_params: dict
    questions: list[dict]
    rejected: list[dict]
    grading: dict
    grade: dict
    mastery_update: dict | None
    diagnosis: list[dict]
    recommendations: list[dict]
    trace: Annotated[list[str], operator.add]


def format_context(docs: list[dict]) -> str:
    lines = []
    for i, d in enumerate(docs, 1):
        m = d["metadata"]
        where = f"{m['title']}, p.{m['page']}" + (f", {m['section']}" if m.get("section") else "")
        lines.append(f"[{i}] ({where})\n{d['text']}")
    return "\n\n".join(lines)


def citation(n: int, d: dict) -> dict:
    m = d["metadata"]
    return {"n": n, "chunk_id": d["chunk_id"], "doc_id": m["doc_id"], "title": m["title"],
            "page": m["page"], "section": m.get("section", ""), "doc_type": m["doc_type"],
            "pdf_url": m.get("pdf_url", ""), "snippet": d["text"][:300]}


def cited_numbers(text: str) -> list[int]:
    return sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})


def merge_unique(*lists: list[dict], limit: int = 8) -> list[dict]:
    seen, out = set(), []
    for lst in lists:
        for d in lst:
            if d["chunk_id"] not in seen:
                seen.add(d["chunk_id"])
                out.append(d)
    return out[:limit]


class CopilotAgent:
    def __init__(self, retriever: Retriever, students: StudentModel, llm: BaseChatModel,
                 fast_llm: BaseChatModel | None = None, retrieval_mode: str = "hybrid_rerank"):
        self.retriever = retriever
        self.students = students
        self.llm = llm
        self.fast = fast_llm or llm
        self.mode = retrieval_mode
        self.graph = self._build()

    # ------------------------------------------------------------------ routing
    def router(self, s: AgentState) -> dict:
        if s.get("intent"):  # the API can force the intent (quiz / grade buttons in the UI)
            return {"search_query": s.get("search_query") or s.get("message", ""),
                    "language": s.get("language", "fr"), "trace": [f"router: intent={s['intent']} (forced)"]}
        d = invoke_json(self.fast, P.ROUTER_SYSTEM.format(concepts=CONCEPT_LIST), s["message"], RouteDecision)
        return {"intent": d.intent, "language": d.language, "search_query": d.search_query or s["message"],
                "concept": d.concept, "attempts": 0,
                "trace": [f"router: intent={d.intent}, lang={d.language}, concept={d.concept}"]}

    # ------------------------------------------------------------------ ask
    def retrieve(self, s: AgentState) -> dict:
        q = s["search_query"]
        docs = self.retriever.search(q, k=6, mode=self.mode)
        if s.get("concept"):
            docs = merge_unique(self.retriever.search(q, k=3, mode=self.mode,
                                                      filters=Filters(concept=s["concept"])), docs)
        return {"docs": docs, "trace": [f"retrieve: '{q}' -> {len(docs)} chunks"]}

    def answer(self, s: AgentState) -> dict:
        history = "\n".join(f"{h['role']}: {h['content'][:300]}" for h in (s.get("history") or [])[-4:])
        text = invoke_text(self.llm, P.ANSWER_SYSTEM.format(language=s.get("language", "fr")),
                           P.ANSWER_USER.format(context=format_context(s["docs"]), history=history or "—",
                                                question=s["message"]))
        return {"answer": text, "trace": ["answer: generated"]}

    def verify(self, s: AgentState) -> dict:
        nums = cited_numbers(s["answer"])
        bad_refs = [n for n in nums if n < 1 or n > len(s["docs"])]
        refuses = "ne trouve pas" in s["answer"].lower()
        if not nums and not refuses:
            v = VerifyResult(supported=False, unsupported_claims=["aucune citation"], better_query=None)
        else:
            v = invoke_json(self.fast, P.VERIFY_SYSTEM,
                            P.VERIFY_USER.format(context=format_context(s["docs"]), answer=s["answer"]),
                            VerifyResult)
        supported = v.supported and not bad_refs
        return {"verified": supported, "unsupported": v.unsupported_claims + [f"citation [{n}] invalide" for n in bad_refs],
                "search_query": v.better_query or s["search_query"],
                "attempts": s.get("attempts", 0) + (0 if supported else 1),
                "trace": [f"verify: supported={supported}"]}

    def after_verify(self, s: AgentState) -> str:
        if not s["verified"] and s["attempts"] <= MAX_RETRIES:
            return "retrieve"
        return "finalize_answer"

    def finalize_answer(self, s: AgentState) -> dict:
        nums = [n for n in cited_numbers(s["answer"]) if 1 <= n <= len(s["docs"])]
        cits = [citation(n, s["docs"][n - 1]) for n in nums]
        answer = s["answer"]
        if not s.get("verified"):
            answer += ("\n\n⚠️ Certaines parties de cette réponse ne sont pas entièrement confirmées par le "
                       "cours. Vérifie avec les extraits cités.")
        return {"answer": answer, "citations": cits, "trace": [f"finalize: {len(cits)} citations"]}

    # ------------------------------------------------------------------ quiz
    def plan_quiz(self, s: AgentState) -> dict:
        params = {"n": 3, "kinds": ["qcm", "short", "analysis"], "difficulty": "bac", **(s.get("quiz_params") or {})}
        concepts = [c for c in params.get("concepts") or [] if c in CONCEPTS]
        if not concepts and s.get("concept"):
            concepts = [s["concept"]]
        reason = "demandé"
        if not concepts:  # adaptive: let the student model choose
            recs = self.students.recommend(s["student_id"], n=min(params["n"], 3))
            concepts, reason = [r["concept"] for r in recs], "recommandé par le modèle élève"
        docs = []
        for c in concepts:
            label = CONCEPTS[c].label
            docs.append(self.retriever.search(label, k=3, mode=self.mode,
                                              filters=Filters(concept=c, doc_types=["cours", "resume"])))
            docs.append(self.retriever.search(label, k=2, mode=self.mode,
                                              filters=Filters(concept=c, doc_types=["bac_sujet", "bac_corrige",
                                                                                    "serie", "devoir"])))
        merged = merge_unique(*docs, limit=10)
        params["concepts"] = concepts
        return {"quiz_params": params, "docs": merged, "questions": [], "rejected": [], "attempts": 0,
                "trace": [f"plan_quiz: concepts={concepts} ({reason}), {len(merged)} chunks"]}

    def generate_questions(self, s: AgentState) -> dict:
        p = s["quiz_params"]
        missing = p["n"] - len(s.get("questions") or [])
        labels = ", ".join(f"{c} ({CONCEPTS[c].label})" for c in p["concepts"])
        out = invoke_json(self.llm, P.QUIZ_SYSTEM.format(concepts=CONCEPT_LIST),
                          P.QUIZ_USER.format(n=missing, concept_labels=labels, kinds=", ".join(p["kinds"]),
                                             difficulty=p["difficulty"], context=format_context(s["docs"])),
                          QuizOut)
        return {"questions": (s.get("questions") or []) + [{**q.model_dump(), "validated": False}
                                                           for q in out.questions[:missing]],
                "trace": [f"generate_questions: {len(out.questions[:missing])} draft(s)"]}

    def validate_questions(self, s: AgentState) -> dict:
        pending = [(i, q) for i, q in enumerate(s["questions"]) if not q["validated"]]
        listing = "\n".join(f"#{i}: {q['question']} | options={q['options']} | réponse modèle: {q['answer']} "
                            f"| sources={q['source_ids']}" for i, q in pending)
        verdicts = invoke_json(self.fast, P.VALIDATE_SYSTEM,
                               P.VALIDATE_USER.format(context=format_context(s["docs"]), questions=listing),
                               Verdicts)
        valid_idx = {v.index for v in verdicts.verdicts if v.valid}
        reasons = {v.index: v.reason for v in verdicts.verdicts}
        kept, rejected = [], list(s.get("rejected") or [])
        for i, q in enumerate(s["questions"]):
            if q["validated"] or i in valid_idx:
                kept.append({**q, "validated": True})
            else:
                rejected.append({"question": q["question"], "reason": reasons.get(i, "non vérifiable")})
        return {"questions": kept, "rejected": rejected, "attempts": s.get("attempts", 0) + 1,
                "trace": [f"validate_questions: kept {len(kept)}, rejected {len(rejected)} total"]}

    def after_validate(self, s: AgentState) -> str:
        if len(s["questions"]) < s["quiz_params"]["n"] and s["attempts"] <= MAX_RETRIES:
            return "generate_questions"
        return "finalize_quiz"

    def finalize_quiz(self, s: AgentState) -> dict:
        questions = []
        for i, q in enumerate(s["questions"]):
            srcs = [citation(n, s["docs"][n - 1]) for n in q["source_ids"] if 1 <= n <= len(s["docs"])]
            questions.append({**q, "id": f"q{i + 1}", "max_points": sum(r["points"] for r in q["rubric"]) or 1.0,
                              "concept": q.get("concept") or s["quiz_params"]["concepts"][0],
                              "sources": srcs})
        return {"questions": questions, "trace": [f"finalize_quiz: {len(questions)} questions"]}

    # ------------------------------------------------------------------ grade
    def prepare_grading(self, s: AgentState) -> dict:
        g = dict(s["grading"])
        q = g["question"]
        docs = merge_unique(
            self.retriever.search(q, k=3, mode=self.mode, filters=Filters(has_correction=True)),
            self.retriever.search(q, k=5, mode=self.mode), limit=7)
        if not g.get("rubric"):
            r = invoke_json(self.llm, P.RUBRIC_SYSTEM.format(max_points=g.get("max_points", 2)),
                            f"Question : {q}\n\nExtraits :\n{format_context(docs)}", RubricOut)
            g["rubric"] = [x.model_dump() for x in r.rubric]
            g["reference"] = g.get("reference") or r.reference
        return {"grading": g, "docs": docs, "trace": [f"prepare_grading: {len(docs)} chunks, "
                                                      f"{len(g['rubric'])} criteria"]}

    def grade_answer(self, s: AgentState) -> dict:
        g = s["grading"]
        rubric = "\n".join(f"- {r['criterion']} ({r['points']} pt)" for r in g["rubric"])
        out = invoke_json(self.llm, P.GRADE_SYSTEM.format(language=s.get("language", "fr"), concepts=CONCEPT_LIST),
                          P.GRADE_USER.format(question=g["question"], rubric=rubric,
                                              reference=g.get("reference") or "—",
                                              context=format_context(s["docs"]),
                                              student_answer=g["student_answer"]),
                          GradeOut).normalized()
        cits = [citation(n, s["docs"][n - 1]) for n in cited_numbers(out.feedback) if 1 <= n <= len(s["docs"])]
        return {"grade": {**out.model_dump(), "citations": cits},
                "trace": [f"grade_answer: {out.score}/{out.max_score}"]}

    def update_student(self, s: AgentState) -> dict:
        grade, g = s["grade"], s["grading"]
        concept = g.get("concept") or grade.get("concept") or s.get("concept")
        update, diagnosis = None, []
        if concept in CONCEPTS and grade["max_score"] > 0:
            update = self.students.record_attempt(s["student_id"], concept, grade["score"], grade["max_score"],
                                                  g["question"])
            if grade["score"] / grade["max_score"] < 0.6:
                diagnosis = self.students.diagnose(s["student_id"], concept)
        recs = self.students.recommend(s["student_id"], n=3)
        return {"mastery_update": update, "diagnosis": diagnosis, "recommendations": recs,
                "trace": [f"update_student: {update}"]}

    # ------------------------------------------------------------------ progress
    def progress(self, s: AgentState) -> dict:
        m = self.students.mastery(s["student_id"])
        recs = self.students.recommend(s["student_id"], n=3)
        evaluated = [x for x in m if x["n_attempts"]]
        weak = [x["label"] for x in evaluated if x["status"] in ("à revoir", "fragile")]
        lines = [f"Concepts évalués : {len(evaluated)}/{len(m)}."]
        if weak:
            lines.append("Points à renforcer : " + ", ".join(weak) + ".")
        lines.append("Je te conseille de travailler ensuite : " +
                     ", ".join(f"{CONCEPTS[r['concept']].label} ({r['reason']})" for r in recs) + ".")
        return {"answer": "\n".join(lines), "recommendations": recs, "citations": [],
                "trace": ["progress: report"]}

    # ------------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(AgentState)
        for name in ("router", "retrieve", "answer", "verify", "finalize_answer", "plan_quiz",
                     "generate_questions", "validate_questions", "finalize_quiz", "prepare_grading",
                     "grade_answer", "update_student", "progress"):
            g.add_node(name, getattr(self, name))
        g.add_edge(START, "router")
        g.add_conditional_edges("router", lambda s: s["intent"],
                                {"ask": "retrieve", "quiz": "plan_quiz", "grade": "prepare_grading",
                                 "progress": "progress"})
        g.add_edge("retrieve", "answer")
        g.add_edge("answer", "verify")
        g.add_conditional_edges("verify", self.after_verify, ["retrieve", "finalize_answer"])
        g.add_edge("finalize_answer", END)
        g.add_edge("plan_quiz", "generate_questions")
        g.add_edge("generate_questions", "validate_questions")
        g.add_conditional_edges("validate_questions", self.after_validate, ["generate_questions", "finalize_quiz"])
        g.add_edge("finalize_quiz", END)
        g.add_edge("prepare_grading", "grade_answer")
        g.add_edge("grade_answer", "update_student")
        g.add_edge("update_student", END)
        g.add_edge("progress", END)
        return g.compile()

    # ------------------------------------------------------------------ public API
    def run(self, **state: Any) -> AgentState:
        state.setdefault("student_id", "demo")
        state.setdefault("trace", [])
        state.setdefault("attempts", 0)
        self.students.ensure_student(state["student_id"])
        return self.graph.invoke(state)

    def chat(self, student_id: str, message: str, history: list[dict] | None = None) -> AgentState:
        return self.run(student_id=student_id, message=message, history=history or [])

    def quiz(self, student_id: str, n: int = 3, concepts: list[str] | None = None,
             kinds: list[str] | None = None, difficulty: str = "bac") -> AgentState:
        params = {"n": n, "concepts": concepts or [], "difficulty": difficulty}
        if kinds:
            params["kinds"] = kinds
        return self.run(student_id=student_id, intent="quiz", message="quiz", quiz_params=params)

    def grade(self, student_id: str, question: str, student_answer: str, rubric: list[dict] | None = None,
              reference: str | None = None, concept: str | None = None, max_points: float = 2.0,
              language: str = "fr") -> AgentState:
        return self.run(student_id=student_id, intent="grade", message=student_answer, language=language,
                        grading={"question": question, "student_answer": student_answer, "rubric": rubric,
                                 "reference": reference, "concept": concept, "max_points": max_points})
