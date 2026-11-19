"""A scripted chat model: answers depend on which prompt it receives. Lets us test the whole
LangGraph agent offline (no Groq key, deterministic)."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedLLM(BaseChatModel):
    responses: dict[str, Any] = {}
    calls: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kw) -> ChatResult:
        system = messages[0].content
        self.calls.append(system[:40])
        for key, reply in self.responses.items():
            if key in system:
                reply = reply(messages) if callable(reply) else reply
                text = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(text))])
        raise AssertionError(f"no scripted reply for prompt: {system[:80]}")
