"""Structure-aware chunking.

- Chunks never cross a page boundary, so every citation points to one exact page.
- Exam documents (bac, devoirs, séries) are split on their natural units ("Exercice 2",
  "Partie I", "Question 3") and the current heading is kept as `section` metadata.
- Long sections are split on paragraphs, then sentences, with a small overlap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..concepts import normalize, tag_concepts
from .pdf_loader import PageText

HEADING_RE = re.compile(
    r"^\s*((exercice|exercise|partie|premiere partie|deuxieme partie|probleme|question|document|"
    r"chapitre|[ivx]+\s*[-.)]|[A-D]\s*[-.)])[^\n]{0,80})$",
    re.IGNORECASE,
)
POINTS_RE = re.compile(r"\((\d+(?:[.,]\d+)?)\s*(?:pts?|points?)\)", re.IGNORECASE)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    page: int
    text: str
    section: str = ""
    points: float | None = None
    concepts: list[str] = field(default_factory=list)
    ocr: bool = False


def _split_long(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    units = re.split(r"(?<=[.!?;:])\s+|\n", text)
    parts, current = [], ""
    for unit in units:
        if not unit.strip():
            continue
        if len(current) + len(unit) + 1 > size and current:
            parts.append(current.strip())
            current = current[-overlap:] + " " + unit  # overlap keeps context across the cut
        else:
            current = f"{current} {unit}" if current else unit
    if current.strip():
        parts.append(current.strip())
    # hard cut for pathological units (e.g. OCR without punctuation)
    out = []
    for p in parts:
        while len(p) > size * 1.5:
            out.append(p[:size])
            p = p[size - overlap:]
        out.append(p)
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    """Split a page into (heading, body) blocks."""
    blocks: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if len(line) < 90 and HEADING_RE.match(normalize(line)):
            blocks.append((line.strip(), [line]))
        else:
            blocks[-1][1].append(line)
    return [(h, "\n".join(body).strip()) for h, body in blocks if "\n".join(body).strip()]


def chunk_document(
    doc_id: str,
    pages: list[PageText],
    doc_concepts: list[str] | None = None,
    size: int = 900,
    overlap: int = 150,
    min_chars: int = 80,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    last_heading = ""
    for page in pages:
        for heading, body in _sections(page.text):
            heading = heading or last_heading
            last_heading = heading
            pending = ""
            pieces = _split_long(body, size, overlap)
            for piece in pieces:
                # merge tiny fragments (titles, isolated lines) into the next piece
                piece = f"{pending}\n{piece}".strip() if pending else piece
                if len(piece) < min_chars and piece is not pieces[-1]:
                    pending = piece
                    continue
                pending = ""
                pts = POINTS_RE.search(heading + " " + piece[:120])
                concepts = tag_concepts(piece) or list(doc_concepts or [])
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}:p{page.page}:c{len(chunks)}",
                        doc_id=doc_id,
                        page=page.page,
                        text=piece,
                        section=heading[:90],
                        points=float(pts.group(1).replace(",", ".")) if pts else None,
                        concepts=concepts[:3],
                        ocr=page.ocr,
                    )
                )
    return [c for c in chunks if len(c.text) >= 30]
