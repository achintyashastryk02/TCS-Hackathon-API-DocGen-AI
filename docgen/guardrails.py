"""Input and output guardrails (deterministic - no LLM involved)."""
from __future__ import annotations

import re
from dataclasses import dataclass

NOT_SPECIFIED = "Not specified in the provided input."

# ---------------------------------------------------------------- input side
SECRET_PATTERNS = [  # literal tokens -> replaced entirely
    re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
]
_KEYS = r"(?:password|passwd|secret|token|api[_-]?key)"
# key = "value"  /  "key": "value"   (quoted values only, to avoid redacting plain code)
QUOTED_CRED = re.compile(rf"(?i)(\b[\w\-]*{_KEYS}[\w\-]*['\"]?\s*[:=]\s*)(['\"])([^\s'\"]{{6,}})\2")
# YAML style  db_password: hunter2abc
YAML_CRED = re.compile(rf"(?im)^(\s*[\w\-]*{_KEYS}[\w\-]*\s*:\s*)([^\s'\"#{{\[][^\s#]{{5,}})\s*$")

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any )?(the )?(previous|prior|above)",
    r"you are now\b",
    r"reveal (your|the) (system )?prompt",
    r"override (the )?(system|safety)",
    r"</?(system|assistant)>",
]


def redact_secrets(text: str) -> tuple[str, int]:
    """Mask likely secrets. Returns (clean_text, number_of_redactions)."""
    count = 0
    for pat in SECRET_PATTERNS:
        text, n = pat.subn("[REDACTED]", text)
        count += n
    text, n = QUOTED_CRED.subn(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]{m.group(2)}", text)
    count += n
    text, n = YAML_CRED.subn(lambda m: f"{m.group(1)}[REDACTED]", text)
    count += n
    return text, count


def scan_injection(text: str) -> list[str]:
    hits = [p for p in INJECTION_PATTERNS if re.search(p, text, re.I)]
    if hits:
        return ["Instruction-like text found inside the input. It is treated strictly as data and will not be followed."]
    return []


def number_lines(text: str) -> str:
    lines = text.splitlines() or [""]
    width = len(str(len(lines)))
    return "\n".join(f"L{i:>{width}}| {ln}" for i, ln in enumerate(lines, 1))


# --------------------------------------------------------------- output side
HYPE_WORDS = [
    "cutting-edge", "state-of-the-art", "industry-leading", "revolutionary", "seamless",
    "best-in-class", "world-class", "blazing", "game-changing", "next-generation", "groundbreaking",
]
URL_RE = re.compile(r"https?://[^\s)>\]\"']+")
VERSION_RE = re.compile(r"(?<![\w.])v?\d+\.\d+(?:\.\d+)+(?![\w.])")
INLINE_CODE_RE = re.compile(r"`([^`\n]{3,80})`")
EVIDENCE_REF_RE = re.compile(r"^L\d+(\s*[-–]\s*L?\d+)?$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")


def sanitize_output(text: str) -> str:
    """Remove chatter, wrapping fences and raw HTML from the model output."""
    t = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", t, re.S)
    if m:
        t = m.group(1).strip()
    t = re.sub(r"(?is)<\s*(script|style|iframe)[^>]*>.*?<\s*/\s*\1\s*>", "", t)
    t = re.sub(r"(?i)</?\s*(script|style|iframe|object|embed|img|a)\b[^>]*>", "", t)
    first = t.find("\n# ")
    if not t.startswith("#") and first != -1:  # drop "Sure, here is..." preambles
        t = t[first + 1 :]
    return t.strip()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def _split_sections(doc: str, titles: list[str]) -> dict[str, str]:
    """Map required section title -> its body text."""
    wanted = {_norm(t): t for t in titles}
    out: dict[str, list[str]] = {}
    current = None
    for line in doc.splitlines():
        m = HEADING_RE.match(line)
        if m:
            name = re.sub(r"^\d+[\.\)]\s*", "", m.group(2)).strip()
            key = _norm(name)
            current = wanted.get(key)
            if current is not None:
                out.setdefault(current, [])
            continue
        if current is not None:
            out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def check_output(doc: str, source: str, sections: list[dict]) -> list[str]:
    """Return a list of human-readable guardrail violations (empty = pass)."""
    issues: list[str] = []
    if not doc.lstrip().startswith("# "):
        issues.append("Document must start with a single '# <Project title>' heading.")
    if len(doc) < 400:
        issues.append("Document is too short to be complete.")

    titles = [s["title"] for s in sections]
    bodies = _split_sections(doc, titles)
    for s in sections:
        t = s["title"]
        if t not in bodies:
            issues.append(f"Missing required section: '{t}'.")
            continue
        if not bodies[t].strip():
            issues.append(f"Section '{t}' is empty (use: {NOT_SPECIFIED}).")
        if s.get("evidence", True) and "evidence:" not in bodies[t].lower():
            issues.append(f"Section '{t}' has no 'Evidence:' line citing the input.")

    src = source.lower()
    body_no_evidence = "\n".join(
        ln for ln in doc.splitlines() if not ln.strip().lower().startswith(("evidence:", "_evidence:", "*evidence:"))
    )

    for hype in HYPE_WORDS:
        if hype in doc.lower():
            issues.append(f"Unsupported marketing wording: '{hype}'.")

    for url in sorted(set(URL_RE.findall(body_no_evidence))):
        if url.rstrip(".,;").lower() not in src:
            issues.append(f"URL not present in input: {url}")

    for ver in sorted(set(VERSION_RE.findall(body_no_evidence))):
        if ver.lower().lstrip("v") not in src:
            issues.append(f"Version number not present in input: {ver}")

    for tok in sorted(set(INLINE_CODE_RE.findall(body_no_evidence))):
        t = tok.strip()
        if EVIDENCE_REF_RE.match(t) or t.lower() in src or _norm(t) in _norm(source):
            continue
        issues.append(f"Identifier/command not found in input: `{t}`")

    return issues[:25]
