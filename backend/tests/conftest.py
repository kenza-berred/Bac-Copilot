import json
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COURSE_PAGES = [
    "Chapitre : La réponse immunitaire spécifique\n"
    "Les lymphocytes B reconnaissent l'antigène et se différencient en plasmocytes qui sécrètent "
    "des anticorps (immunoglobulines). Les anticorps neutralisent l'antigène en formant des complexes "
    "immuns, éliminés ensuite par phagocytose. Les lymphocytes LT4 sécrètent l'interleukine qui active "
    "la sélection clonale.",
    "Exercice 2 (4 points)\nLes lymphocytes LT8 deviennent des lymphocytes cytotoxiques qui détruisent "
    "les cellules infectées par lyse. C'est la médiation cellulaire. La mémoire immunitaire explique "
    "l'efficacité de la vaccination.",
]
GENETICS_PAGES = [
    "Le brassage interchromosomique a lieu en anaphase I de la méiose. Le brassage intrachromosomique "
    "résulte du crossing-over en prophase I, au niveau des chiasmas. Il produit des gamètes recombinés.",
]


def make_pdf(path: Path, pages: list[str]) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
    doc.save(path)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    catalog = [
        {"doc_id": "doc-1", "title": "Cours immunité", "doc_type": "cours", "has_correction": False,
         "concepts": ["reponse_specifique"], "year": None, "session": None, "pdf_url": "", "page_url": ""},
        {"doc_id": "doc-2", "title": "Résumé Brassages", "doc_type": "resume", "has_correction": False,
         "concepts": ["brassage"], "year": None, "session": None, "pdf_url": "", "page_url": ""},
    ]
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), "utf-8")
    make_pdf(tmp_path / "raw" / "doc-1.pdf", COURSE_PAGES)
    make_pdf(tmp_path / "raw" / "doc-2.pdf", GENETICS_PAGES)
    return tmp_path
