"""LLM access (Groq via LangChain) and robust JSON output parsing.

We ask for JSON in the prompt and validate it with Pydantic instead of relying on provider-specific
structured-output features: it works with any chat model (including the fake models used in tests),
and on a parse error we retry once, showing the model its mistake.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from .config import settings

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=4)
def get_llm(fast: bool = False, temperature: float = 0.2) -> BaseChatModel:
    from langchain_groq import ChatGroq

    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing — copy .env.example to .env and add your key.")
    return ChatGroq(model=settings.groq_fast_model if fast else settings.groq_model,
                    temperature=temperature, api_key=settings.groq_api_key, max_retries=3)


def extract_json(text: str) -> dict | list:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("no JSON object in model output")
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def invoke_json(llm: BaseChatModel, system: str, user: str, schema: type[T], retries: int = 1) -> T:
    messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
    last_error = None
    for _ in range(retries + 1):
        reply = llm.invoke(messages)
        content = reply.content if isinstance(reply.content, str) else str(reply.content)
        try:
            return schema.model_validate(extract_json(content))
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_error = e
            messages += [AIMessage(content),
                         HumanMessage(f"Ta réponse n'est pas un JSON valide pour le schéma demandé ({e}). "
                                      "Renvoie UNIQUEMENT le JSON corrigé.")]
    raise ValueError(f"LLM did not return valid JSON: {last_error}")


def invoke_text(llm: BaseChatModel, system: str, user: str) -> str:
    reply = llm.invoke([SystemMessage(system), HumanMessage(user)])
    return reply.content if isinstance(reply.content, str) else str(reply.content)
