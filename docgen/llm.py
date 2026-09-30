"""LLM factory + ordered fallback (OpenRouter -> Groq -> Ollama)."""
from __future__ import annotations

import os
from typing import Callable, Optional

from .config import ModelSpec, model_chain

# event kinds: "trying" | "failed" | "using"
EventCb = Callable[[str, ModelSpec, Optional[Exception]], None]


class AllModelsFailed(RuntimeError):
    pass


def build_chat_model(spec: ModelSpec):
    if spec.provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=spec.model,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
            timeout=90,
            max_retries=0,
        )
    if spec.provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=spec.model, temperature=0, timeout=60, max_retries=0)
    if spec.provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=spec.model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,
        )
    raise ValueError(f"Unknown provider: {spec.provider}")


def _to_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # multi-part content blocks
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


class FallbackLLM:
    """Tries each model in order; the first non-empty answer wins."""

    def __init__(self, chain: list[ModelSpec] | None = None, on_event: EventCb | None = None):
        self.chain = chain if chain is not None else model_chain()
        self.on_event = on_event
        self.last_used: ModelSpec | None = None

    @property
    def last_label(self) -> str:
        return self.last_used.label if self.last_used else "unknown"

    def _emit(self, kind, spec, err=None):
        if self.on_event:
            try:
                self.on_event(kind, spec, err)
            except Exception:  # UI callbacks must never break generation
                pass

    def invoke(self, messages) -> str:
        errors: list[str] = []
        for spec in self.chain:
            self._emit("trying", spec)
            try:
                text = _to_text(build_chat_model(spec).invoke(messages).content).strip()
                if not text:
                    raise ValueError("empty response")
                self.last_used = spec
                self._emit("using", spec)
                return text
            except Exception as exc:  # noqa: BLE001 - any provider error -> next model
                errors.append(f"{spec.label}: {type(exc).__name__}: {str(exc)[:160]}")
                self._emit("failed", spec, exc)
        raise AllModelsFailed("All models failed:\n" + "\n".join(errors))
