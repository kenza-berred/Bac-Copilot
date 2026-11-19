# Relevance annotation — how `relevant` was filled in `eval_questions.jsonl`

**Unit**: one `(doc_id, page)` pair = one page that, on its own, contains the answer
(or the essential part of it). A retrieved chunk counts as relevant if it comes from one of those pages.

**Pooling**: candidates were collected *independently of the four retrieval modes*. For each question we ran
targeted keyword / regex searches over every indexed page (`data/processed/chunks.jsonl`, 5,069 chunks),
using the question's key terms and their usual variants in the course (e.g. *Leydig*, *cellules interstitielles*,
*testostérone*). The 10–12 best-matching pages were read and a page was kept only if it explicitly states the answer.
Pages from duplicate documents (identical PDFs indexed twice, e.g. `bac-2008-principale-corrige-53` and
`bac-2008-controle-corrige-55`) are labelled together.

Keyword pooling makes the labels independent of the systems being compared, but it may slightly favour BM25.
That bias should be stated in the report.

**Multilingual questions** (q055–q060, Arabic and *derja*) reuse the labels of their French twin
(q049, q017, q031, q014, q024, q042), because the corpus is in French.

**Questions without an answer in the corpus**: q021 (lignée pure), q030 (conseil génétique),
q047 (étapes de la phagocytose) and q048 (signes de l'inflammation). No page states the answer, so
they have `relevant: []` and `in_corpus: false`. The retrieval benchmark skips them (56 questions are scored).
In the generation benchmark, a good system should say it doesn't find the answer in the course.

**Size**: 56 questions with 1–7 relevant pages each (mean 4.5).

**Who labelled**: the first pass was done with Claude (AI assistant) from the page texts, following the rules above.
The author must re-check the labels before quoting the results (`python evaluation/annotate.py --redo qXXX`
to redo one question). The labels were done by a single annotator, so there is no inter-annotator agreement.
