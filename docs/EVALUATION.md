# Evaluation protocol

All results are written to `evaluation/results/*.json`, and each script also prints a Markdown table you can paste into the report.

## 1. Retrieval

- **Question set**: `evaluation/data/eval_questions.jsonl` has 64 questions:
  - 54 in French, 3 in Arabic and 3 in *derja*, covering all 16 concepts;
  - 4 out-of-scope questions, so the system can be tested on refusing.
  
  Check every reference answer, and replace or add questions taken from real bac papers (that is a strong point for the report).
- **Relevance labels**: `python evaluation/annotate.py`. For each question, the top results of the 4 retrieval modes are pooled, and you mark which passages actually answer it. The labels are `(doc_id, page)` pairs. Budget about 2 hours for 60 questions.
- **Metrics**: Recall@1/3/5/10, Hit@5, MRR, nDCG@5 and median latency, for each mode (dense, bm25, hybrid, hybrid_rerank). Add `--by-language` to see the French / Arabic / *derja* breakdown.
- **Suggested ablations**:
  - chunk size of 500 vs 900 vs 1400, each in its own `DATA_DIR`;
  - with vs without OCR;
  - E5-base vs a smaller multilingual embedding model.

## 2. Answer generation

`run_generation_eval.py` compares a plain RAG **baseline** with the full **agent** on the same questions.

| Metric | How it's measured |
|---|---|
| faithfulness | LLM judge: share of the answer's claims supported by the retrieved excerpts |
| correctness | LLM judge: 0, 0.5 or 1 against the reference answer |
| citation_valid | Code check: every `[n]` points to an existing excerpt |
| citation_precision | Share of cited excerpts that were labelled relevant |
| refusal_ok | For out-of-scope questions: did the system say it doesn't know? |
| latency | Seconds per answer |

**Checking the judge**: `--export-human 30` writes 30 answers to `human_check.jsonl`. Grade them yourself, then run `judge_agreement.py` (exact agreement and QWK). If the judge disagrees with you too often, say so in the report.

## 3. Auto-grading

1. `make_grading_set.py --n 20` picks passages from official bac corrections. For each one it extracts a question, its official answer and the marking scheme, and drafts 4 student answers (excellent, partial, conceptual error, off-topic).
2. **You** grade each answer with the official marking scheme (`human_score`). This is the ground truth. If you can, add real answers from bac students.
3. `run_grading_eval.py` reports:
   - MAE in points;
   - share of grades within 0.5 point of yours;
   - Pearson correlation;
   - QWK;
   - bias (is the model more lenient than a human?).
4. Ablation: `--generated-rubric` grades without the official marking scheme, to measure what the official scheme adds.

## 4. Student model

- **Knowledge tracing** (`run_kt_eval.py`): next-answer prediction on ASSISTments 2009 skill-builder, a public dataset of real student answers. Compared models:
  - global mean;
  - per-skill mean;
  - BKT with default parameters;
  - BKT with parameters fitted per skill.
  
  Metrics are AUC and RMSE. `--synthetic` runs a check without the dataset.
- **Adaptive practice** (`simulate_students.py`): virtual students with a hidden state of knowledge. A concept can only be learned once its prerequisites are known. Three policies are compared on the share of concepts mastered after N questions: random, curriculum order, and the copilot's recommendations.

  Current result: with 150 students and 100 questions, adaptive reaches **0.866**, sequential 0.826 and random 0.457.

## 5. Limitations to report

- The labelled questions were written by the author, so there is a risk of bias. The relevance labels were done by a single person.
- The LLM judge has its own error rate; report it.
- The simulation depends on its assumptions (learning probability, slip, guess).
- OCR, figures and diagrams; the copyright of the source documents.
