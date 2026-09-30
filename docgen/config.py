"""Environment-driven configuration and the model fallback chain."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class ModelSpec:
    provider: str  # "openrouter" | "groq" | "ollama"
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider} · {self.model}"


def _csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "60000"))
MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "2"))


def model_chain() -> list[ModelSpec]:
    """OpenRouter specific models -> openrouter/free -> Groq -> Ollama.

    Providers without an API key are skipped (Ollama needs none).
    """
    chain: list[ModelSpec] = []
    if os.getenv("OPENROUTER_API_KEY"):
        for m in _csv(
            "OPENROUTER_MODELS",
            "meta-llama/llama-3.3-70b-instruct:free,qwen/qwen3-coder:free,google/gemma-3-27b-it:free",
        )[:3]:
            chain.append(ModelSpec("openrouter", m))
        chain.append(ModelSpec("openrouter", os.getenv("OPENROUTER_FALLBACK_MODEL", "openrouter/free")))
    if os.getenv("GROQ_API_KEY"):
        for m in _csv("GROQ_MODELS", "llama-3.3-70b-versatile"):
            chain.append(ModelSpec("groq", m))
    for m in _csv("OLLAMA_MODELS", "llama3.1"):
        chain.append(ModelSpec("ollama", m))
    return chain
