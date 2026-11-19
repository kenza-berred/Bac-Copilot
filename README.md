# Bac Copilot — SVT

**Adaptive RAG study copilot for Tunisian bac students (section Sciences expérimentales, SVT).**

Students ask questions in French, Arabic or Tunisian *derja* and get answers grounded in real course
material, with every claim cited to the exact page. They take bac-style mock exams that are graded
criterion by criterion like an official *corrigé*, and the copilot tracks their mastery of every
concept so it can send them back to the prerequisite that is actually causing their mistakes.

Module project — AI Engineering.

| Requirement | Where |
|---|---|
| RAG, metadata, citations | `backend/app/ingestion`, `backend/app/retrieval`: page-level chunks with document type, year, session, section, points and concept tags. Hybrid search, reranking, and clickable citations down to the page |
| Document management | `data/catalog.json` (129 documents), incremental re-indexing by SHA-256 with a version per document, Documents page in the UI |
| Tool calling / MCP | `backend/app/mcp_server.py`: 6 MCP tools, plus a client in `scripts/mcp_client_demo.py` |
| LangChain / LangGraph | `backend/app/agent/graph.py`: a router plus three branches (answer, quiz, grade), each with a check-and-retry loop |
| Benchmarking | `evaluation/`: retrieval (Recall@k, MRR, nDCG), generation (faithfulness and correctness scored by an LLM judge, then checked against human grades), auto-grading agreement, knowledge tracing (AUC), adaptive-practice simulation |
| Web interface | `frontend/`: React + Vite |

## Architecture

```
bac-done.com PDFs ──► ingestion (PyMuPDF + OCR, structure-aware chunks, concept tagging)
                         │
                         ▼
                Chroma (E5 multilingual)  +  BM25  ──RRF──► cross-encoder reranker
                         │
     ┌───────────────────┴──────────────────────────────┐
     │              LangGraph agent                     │
     │  router ─► ask:   retrieve ► answer ► verify ⟲   │
     │         ─► quiz:  plan ► generate ► validate ⟲   │◄── Student model (BKT + SM-2 +
     │         ─► grade: rubric ► grade ► update model  │      prerequisite graph), SQLite
     └───────────────────┬──────────────────────────────┘
                         │
          FastAPI (REST) ┴ MCP server (stdio)
                │                │
        React web app      any MCP client
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design choices.

## Data

Source: [bac-done.com](https://bac-done.com), SVT, Sciences expérimentales:
- **81 course documents**: courses, summaries, corrected exercise sets, class tests, revision booklets
- **48 official bac exams**, 2008–2019, main and resit sessions, papers and corrections

`data/catalog.json` holds only metadata. The PDFs are copyrighted: they are downloaded locally and
**never committed** (`data/raw/` is in `.gitignore`).

## Setup

Requirements: Python 3.11+ and Node 18+. For scanned PDFs, also install Tesseract with French
(`sudo apt install tesseract-ocr tesseract-ocr-fra`, or `brew install tesseract tesseract-lang`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add your GROQ_API_KEY (free at console.groq.com)

python scripts/build_catalog.py   # data/catalog.json (already committed)
python scripts/download_bac_done.py --limit 5   # test, then run without --limit
cd backend && python -m app.ingestion.pipeline  # index (re-run anytime: incremental)
```

Run:

```bash
cd backend && uvicorn app.api:app --reload --port 8000      # API
cd frontend && npm install && npm run dev                    # http://localhost:5173
python scripts/mcp_client_demo.py --with-llm                 # MCP demo
```

To use the MCP server from Claude Desktop, add this to its `claude_desktop_config.json`:
```json
{ "mcpServers": { "bac-copilot": { "command": "/abs/path/.venv/bin/python",
  "args": ["-m", "app.mcp_server"], "cwd": "/abs/path/bac-copilot/backend" } } }
```

## Evaluation

See [docs/EVALUATION.md](docs/EVALUATION.md) for the full protocol.

```bash
python evaluation/annotate.py                     # label relevant passages (pooling)
python evaluation/run_retrieval_eval.py --by-language
python evaluation/run_generation_eval.py --export-human 30
python evaluation/make_grading_set.py --n 20      # then fill human_score yourself
python evaluation/run_grading_eval.py
python evaluation/run_kt_eval.py --csv skill_builder_data.csv
python evaluation/simulate_students.py
```

Results so far (run offline, no LLM needed):

| Experiment | Result |
|---|---|
| Adaptive practice simulation (150 virtual students, 100 questions) | adaptive **86.6 %** of concepts mastered vs sequential 82.6 % vs random 45.7 % |
| Knowledge tracing on synthetic sequences (sanity check) | BKT AUC 0.69 vs 0.50 for the global-mean baseline |

## Tests

```bash
cd backend && pytest -q     # 14 tests, offline (scripted LLM + hashing embedder)
```

## Project layout

```
backend/app/
  concepts.py          SVT curriculum concept graph (16 concepts, prerequisites, keyword lexicon)
  ingestion/           pdf_loader (OCR fallback), chunker, incremental pipeline
  retrieval/           embeddings (E5), Chroma store, BM25, hybrid + RRF + reranker
  student/model.py     BKT, SM-2 spaced repetition, diagnosis, recommendations
  agent/               LangGraph graph, prompts, Pydantic schemas
  api.py / mcp_server.py
evaluation/            metrics, benchmarks, annotation tool, seed questions
frontend/              React app
scripts/               catalog, downloader, MCP client demo
docs/                  architecture, evaluation protocol, report outline
```

## Limitations

- OCR quality on handwritten corrections, and figures (graphs, diagrams) that are not described in text.
- The LLM judge and the auto-grader are themselves models. Their agreement with human grades is measured and reported, not assumed.
- BKT parameters are defaults or fitted on ASSISTments (US math), not on Tunisian SVT students.
- Courses on bac-done follow the program as published there. Check them against the official CNP program before any real use.
