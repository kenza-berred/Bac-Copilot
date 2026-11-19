"""Download the SVT PDFs listed in data/catalog.json into data/raw/.

Run this on your own machine (it needs internet access to bac-done.com):

    python scripts/download_bac_done.py            # everything
    python scripts/download_bac_done.py --only bac # only official bac exams
    python scripts/download_bac_done.py --limit 5  # quick test

Be polite to the site: one request at a time with a delay. Already-downloaded files are skipped.
The PDFs are copyrighted material — keep them local, never commit them.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog.json"
RAW = ROOT / "data" / "raw"
HEADERS = {"User-Agent": "bac-copilot academic project (student RAG prototype)"}


def find_pdf_on_page(client: httpx.Client, page_url: str) -> str | None:
    """Fallback: open the document page and look for the uploaded PDF link."""
    r = client.get(page_url)
    if r.status_code != 200:
        return None
    m = re.search(r"(https?://bac-done\.com)?(/public/uploads/documents/[^\"'\s]+\.pdf)", r.text)
    return f"https://bac-done.com{m.group(2)}" if m else None


def download(doc: dict, client: httpx.Client) -> str:
    target = RAW / f"{doc['doc_id']}.pdf"
    if target.exists() and target.stat().st_size > 1000:
        return "skip"
    urls = [doc["pdf_url"]]
    for attempt, url in enumerate(urls):
        r = client.get(url)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            target.write_bytes(r.content)
            return "ok"
        if attempt == 0 and doc["doc_type"] not in ("bac_sujet", "bac_corrige"):
            alt = find_pdf_on_page(client, doc["page_url"])
            if alt and alt not in urls:
                urls.append(alt)
    return f"failed ({r.status_code})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["bac", "cours"], default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if args.only == "bac":
        catalog = [d for d in catalog if d["doc_type"].startswith("bac")]
    elif args.only == "cours":
        catalog = [d for d in catalog if not d["doc_type"].startswith("bac")]
    if args.limit:
        catalog = catalog[: args.limit]

    stats: dict[str, int] = {}
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        for i, doc in enumerate(catalog, 1):
            status = download(doc, client)
            stats[status.split()[0]] = stats.get(status.split()[0], 0) + 1
            print(f"[{i}/{len(catalog)}] {doc['doc_id']:<40} {status}")
            if status != "skip":
                time.sleep(args.delay)
    print("Done:", stats)


if __name__ == "__main__":
    main()
