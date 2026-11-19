"""Lazily-built singletons shared by the API and the MCP server."""
from __future__ import annotations

from functools import lru_cache

from .agent.graph import CopilotAgent
from .config import settings
from .llm import get_llm
from .retrieval.hybrid import Retriever
from .student.model import StudentModel


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever.from_settings()


@lru_cache(maxsize=1)
def get_students() -> StudentModel:
    return StudentModel(settings.db_path)


@lru_cache(maxsize=1)
def get_agent() -> CopilotAgent:
    return CopilotAgent(get_retriever(), get_students(), get_llm(), get_llm(fast=True))
