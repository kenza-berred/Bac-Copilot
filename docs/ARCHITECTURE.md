# Architecture and design choices

## 1. Ingestion

| Choice | Why |
|---|---|
| **PyMuPDF**, with **Tesseract (fra)** when a page has less than 60 characters of text | Many bac-done PDFs are scans. The manifest counts OCR pages per document so their quality can be checked. |
| **Chunks never cross a page** | Every citation then points to exactly one page, which the PDF viewer opens. |
| **Split on exam structure** (Exercice, Partie, Question, I-, A-) | Bac papers and corrections are organised by exercise. The heading is kept as `section`, and "(4 points)" is kept as `points`. |
| **Concept tagging per chunk** (keyword lexicon from `concepts.py`), falling back to the document's title-level concepts | Lets the system filter by concept, which adaptive quizzes need. Revision booklets and class tests mix several chapters, so tagging the whole document would be wrong. |
| **Title + section added in front of the chunk text before embedding** | Short chunks ("3) Expliquez...") get their context back. |
| **Incremental updates**: SHA-256 per PDF in `manifest.json`, a `version` counter, old chunks deleted before re-indexing, removed PDFs dropped from the index | Meets the "support for updates" requirement. Re-running ingestion only touches what changed. |

## 2. Retrieval

- **Dense search**: `intfloat/multilingual-e5-base` with the `query:` / `passage:` prefixes. It is multilingual, so a question in Arabic or *derja* can match French course text.
- **BM25**: keyword search with accents removed, French stopwords and light stemming. It catches exact terms (LT8, PPSE, crossing-over) that embeddings blur.
- **Reciprocal Rank Fusion** (k = 60) merges the two lists. It needs no score calibration.
- **Cross-encoder reranker**: `mmarco-mMiniLMv2` (multilingual) re-scores the top 30 candidates.
- All four modes (`dense`, `bm25`, `hybrid`, `hybrid_rerank`) can be selected at query time, which is what the benchmark compares.
- Metadata filters work in both indexes. Each concept has its own boolean flag `c_<concept>`, because Chroma can't filter on "list contains".

## 3. LangGraph agent

One graph with a router and three branches (diagram at the top of `agent/graph.py`).

- **Router** (small, fast model): picks the intent (ask, quiz, grade, progress), detects the language, rewrites the question as a French search query and spots the concept. The API can force the intent when the student clicks a button.
- **Ask** branch: retrieve, then answer with an `[n]` citation after every claim, then verify:
  - a deterministic check that each `[n]` points to an existing excerpt;
  - an LLM check for claims the excerpts don't support.
  
  If the answer fails, it retries once with a better query proposed by the verifier. If it still fails, the answer is shown with an "À vérifier" warning instead of being presented as fact.
- **Quiz** branch: choose concepts (the student's choice, or the student model's recommendation), then retrieve course material and bac questions for each concept, then generate bac-style questions with a rubric, then validate:
  - a verifier rejects questions that can't be answered from their cited sources;
  - the generator fills the gaps once.
- **Grade** branch: retrieve with bac corrections first, then build a rubric (official when available, generated otherwise), then grade criterion by criterion, then update the student model:
  - points awarded are clamped and the total is recomputed in code, so the LLM's arithmetic is never trusted;
  - if the score is under 60 %, the agent diagnoses which prerequisites are weak.
- **Structured outputs**: the model is asked for JSON, which is validated with Pydantic, with one retry that shows the model its error. This works with any provider and with the scripted model used in tests.

## 4. Student model

- **Bayesian Knowledge Tracing** for each (student, concept) pair, with partial credit: the update blends the "correct" and "wrong" posteriors, weighted by the score ratio.
- **SM-2** spaced repetition, with intervals capped at 60 days.
- **Recommendation follows mastery learning.** The frontier is made of unmastered concepts whose prerequisites are all mastered. Concepts already started and closest to mastery come first. Concepts due for review come next. Simulation shows this beats both sequential and random practice (`evaluation/simulate_students.py`). An earlier "least-known concept first" policy did worse than sequential, which is why it was replaced; worth a sentence in the report.

## 5. MCP server

There are six tools: `search_course`, `get_concept_graph`, `get_student_mastery`, `generate_quiz`,
`grade_answer` and `schedule_review`. The server runs over stdio. The demo client lists the tools and calls them. Any MCP client (Claude Desktop, Cursor, IDEs) can use the copilot without the web interface.

## 6. Interface

React + Vite. Four views:
- **Chat**: citations are clickable and open the PDF at the cited page in a side panel; an "Étapes de l'agent" section shows the agent's steps.
- **Mock exam**: a teacher-style correction table, the change in mastery, and the diagnosed prerequisites.
- **Progress**: a mastery heatmap, recommendations and the prerequisite graph.
- **Documents**: the catalogue, version and chunk count per document, and a re-index button.
