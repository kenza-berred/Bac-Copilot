"""Demo MCP client: starts the server over stdio, lists its tools and calls a few of them.

    python scripts/mcp_client_demo.py
    python scripts/mcp_client_demo.py --with-llm   # also generate a quiz and grade an answer (needs GROQ_API_KEY)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def show(title: str, result) -> None:
    print(f"\n=== {title} ===")
    for block in result.content:
        text = getattr(block, "text", str(block))
        try:
            print(json.dumps(json.loads(text), ensure_ascii=False, indent=2)[:1500])
        except json.JSONDecodeError:
            print(text[:1500])


async def main(with_llm: bool) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"], cwd=str(BACKEND),
                                    env=dict(os.environ))  # pass DATA_DIR, model overrides, etc.
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])
            show("search_course", await session.call_tool(
                "search_course", {"query": "rôle des lymphocytes T cytotoxiques", "k": 3}))
            show("get_concept_graph", await session.call_tool("get_concept_graph", {}))
            show("schedule_review", await session.call_tool("schedule_review", {"student_id": "demo"}))
            if with_llm:
                show("generate_quiz", await session.call_tool(
                    "generate_quiz", {"student_id": "demo", "n": 2, "concepts": ["reponse_specifique"]}))
                show("grade_answer", await session.call_tool("grade_answer", {
                    "student_id": "demo", "concept": "reponse_specifique",
                    "question": "Expliquez le rôle des LT8 dans la réponse immunitaire.",
                    "student_answer": "Les LT8 deviennent des LTc qui tuent les cellules infectées."}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true")
    asyncio.run(main(ap.parse_args().with_llm))
