"""Strict input validation: Code Snippet, JSON file, or YAML file only."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field

import yaml

from .config import MAX_INPUT_CHARS
from .guardrails import redact_secrets, scan_injection

SNIPPET_LANGUAGES = ["Python", "JavaScript", "TypeScript", "Java", "Go", "C / C++", "Rust", "SQL", "Shell", "Other"]
ALLOWED_EXT = {"json": (".json",), "yaml": (".yaml", ".yml")}


class InputError(ValueError):
    """Raised with a user-friendly message when the input is unacceptable."""


@dataclass
class ValidatedInput:
    kind: str  # "code" | "json" | "yaml"
    filename: str
    content: str
    language: str | None = None
    warnings: list[str] = field(default_factory=list)


def _finish(kind: str, filename: str, text: str, language: str | None = None) -> ValidatedInput:
    if len(text) > MAX_INPUT_CHARS:
        raise InputError(f"Input is {len(text):,} characters; the limit is {MAX_INPUT_CHARS:,}.")
    warnings = scan_injection(text)
    text, n = redact_secrets(text)
    if n:
        warnings.append(f"{n} possible secret(s) were redacted before being sent to any model.")
    return ValidatedInput(kind, filename, text, language, warnings)


def validate_snippet(text: str, language: str = "Other") -> ValidatedInput:
    text = (text or "").replace("\r\n", "\n")
    if not text.strip():
        raise InputError("The code snippet is empty.")
    if "\x00" in text:
        raise InputError("The snippet contains binary data; paste plain-text code only.")
    if len(text.strip()) < 10:
        raise InputError("The snippet is too short to document (minimum 10 characters).")
    if language == "Python":
        try:
            ast.parse(text)
        except SyntaxError as e:
            raise InputError(f"Invalid Python syntax at line {e.lineno}: {e.msg}") from e
    return _finish("code", f"snippet ({language})", text, language)


def _decode(raw: bytes, filename: str) -> str:
    try:
        return raw.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError as e:
        raise InputError(f"'{filename}' is not valid UTF-8 text.") from e


def validate_file(filename: str, raw: bytes, expected: str) -> ValidatedInput:
    """`expected` is 'json' or 'yaml'."""
    if expected not in ALLOWED_EXT:
        raise InputError("Only JSON or YAML files are accepted.")
    if not filename.lower().endswith(ALLOWED_EXT[expected]):
        raise InputError(f"Expected a {' / '.join(ALLOWED_EXT[expected])} file, got '{filename}'.")
    if not raw:
        raise InputError(f"'{filename}' is empty.")
    text = _decode(raw, filename)

    if expected == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise InputError(f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}") from e
        if not isinstance(data, (dict, list)) or not data:
            raise InputError("JSON must be a non-empty object or array.")
        text = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        try:
            docs = [d for d in yaml.safe_load_all(text) if d is not None]
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise InputError(f"Invalid YAML{where}: {getattr(e, 'problem', str(e))}") from e
        if not docs or not all(isinstance(d, (dict, list)) for d in docs):
            raise InputError("YAML must contain a non-empty mapping or list (not a bare scalar).")
    return _finish(expected, filename, text)
