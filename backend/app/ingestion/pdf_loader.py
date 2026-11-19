"""PDF text extraction with an OCR fallback for scanned pages.

Many bac-done PDFs are scans of handwritten or printed sheets. PyMuPDF gets the text layer when
there is one; when a page has (almost) no text we render it and run Tesseract OCR in French.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 60  # below this, the page is considered scanned


@dataclass
class PageText:
    page: int          # 1-based, matches the PDF viewer
    text: str
    ocr: bool = False


MAX_OCR_SIDE = 3000  # px; huge scans at 300 dpi can exhaust memory (MemoryError) on 32-bit/low-RAM setups


def _ocr_page(page: "pymupdf.Page", dpi: int = 300) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:  # OCR is optional
        log.warning("pytesseract/Pillow not installed: scanned page %s skipped", page.number + 1)
        return ""
    cmd = os.getenv("TESSERACT_CMD") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(cmd):
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        # cap the rendered size: longest side <= MAX_OCR_SIDE px
        longest_pt = max(page.rect.width, page.rect.height) or 1
        dpi = min(dpi, int(MAX_OCR_SIDE * 72 / longest_pt))
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        del pix
        return pytesseract.image_to_string(img, lang="fra")
    except MemoryError:
        log.warning("OCR out of memory on page %s: skipped", page.number + 1)
        return ""
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as e:
        log.warning("OCR failed on page %s: %s", page.number + 1, e)
        return ""


def clean_text(text: str) -> str:
    text = text.replace(" ", " ").replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # words split across lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    # drop page furniture: lone page numbers, site watermarks
    lines = [ln for ln in lines if not re.fullmatch(r"(page\s*)?\d+(\s*/\s*\d+)?", ln, re.I)]
    lines = [ln for ln in lines if "bac-done" not in ln.lower()]
    return "\n".join(lines).strip()


def _extract_pages(path: Path, use_ocr: bool) -> list[PageText]:
    pages: list[PageText] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            text = page.get_text("text")
            ocr = False
            if len(text.strip()) < MIN_TEXT_CHARS and use_ocr:
                text = _ocr_page(page)
                ocr = True
            text = clean_text(text)
            if text:
                pages.append(PageText(page=page.number + 1, text=text, ocr=ocr))
    return pages


def load_pdf(path: Path, use_ocr: bool = True, cache_dir: Path | None = None,
             digest: str | None = None) -> list[PageText]:
    """Extract page texts. With `cache_dir`, results are cached in <cache_dir>/<stem>.json keyed by
    the PDF's sha256 (`digest`), so OCR is never re-run for an unchanged PDF (e.g. chunk-size
    ablations reuse the cached pages)."""
    cache = cache_dir / f"{path.stem}.json" if cache_dir else None
    if cache and cache.exists():
        data = json.loads(cache.read_text("utf-8"))
        if data.get("sha256") == digest and data.get("ocr") == use_ocr:
            return [PageText(**p) for p in data["pages"]]
    pages = _extract_pages(path, use_ocr)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"sha256": digest, "ocr": use_ocr,
                                     "pages": [p.__dict__ for p in pages]}, ensure_ascii=False), "utf-8")
    return pages
