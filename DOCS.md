# Project documentation

## 1. Purpose
Generate hackathon documentation from a code snippet, JSON file or YAML file **without assumptions**.
Every section must cite evidence from the input; missing information is reported, never invented.

## 2. Architecture
```
Streamlit UI (app.py)
   |  validate (docgen/validators.py) + redact secrets + injection scan
   v
LangGraph pipeline (docgen/graph.py)
   load_skill -> analyze -> draft -> guard --issues & retries left--> revise -> guard
                                        \--clean / out of retries--> finalize
   |  every LLM call goes through FallbackLLM (docgen/llm.py)
   v
Editable Markdown  ->  Export PDF / MD (docgen/exporters.py)
```

| Module | Role |
|---|---|
| `app.py` | UI: input, progress + model note, editor/preview, bottom-right export bar |
| `docgen/config.py` | Env config and the ordered model chain |
| `docgen/llm.py` | Provider factory and fallback with event callbacks |
| `docgen/validators.py` | Accepts only code snippet / JSON / YAML; size, syntax, encoding checks |
| `docgen/guardrails.py` | Secret redaction, injection scan, output checks, sanitizer |
| `docgen/skill_loader.py` | Loads the documentation skill into the agent's prompt |
| `docgen/prompts.py` | Grounding rules and node prompts |
| `docgen/graph.py` | LangGraph state machine |
| `docgen/exporters.py` | Markdown and PDF (ReportLab) export |
| `skills/documentation/` | The skill: `SKILL.md`, `sections.yaml`, `references/` |

## 3. The documentation skill
`skills/documentation/` is loaded by the `load_skill` node and injected into the system prompt of every
LLM call. `sections.yaml` is also read by the guardrail node, so the required structure is enforced,
not just requested. Default sections: Project Overview, Problem Statement, Proposed Solution, Key Features,
System Architecture, Technology Stack, Input and Configuration Analysis, Implementation Details,
Setup and Installation, Usage Instructions, Security and Data Handling, Testing and Validation,
Limitations and Known Gaps, Future Scope, Team and Submission Details, Information Gaps.

> The default list is a general hackathon structure. Adjust it to your event's official parameters.

## 4. Guardrails
**Input:** type restricted to snippet/JSON/YAML; JSON/YAML must parse; Python snippets must compile;
UTF-8 only; size limit (`MAX_INPUT_CHARS`); likely secrets redacted before any model call;
instruction-like text in the input is flagged and treated as data.

**Prompt:** facts-only rules, temperature 0, source wrapped in `<source>` tags with line numbers,
a fact-sheet step before drafting, mandatory phrase `Not specified in the provided input.` for gaps.

**Output (deterministic checks):** starts with a title; all required sections present; each section
has an `Evidence:` line; no URLs, version numbers or backticked identifiers absent from the input;
no marketing wording; HTML stripped. Failures trigger up to `MAX_REVISIONS` automatic revisions;
if issues remain they are shown to the user rather than hidden.

## 5. Model fallback
Order: OpenRouter specific free models (max 3) -> `openrouter/free` -> Groq -> Ollama.
Providers without a key are skipped. Any exception or empty answer moves to the next model.
The UI shows `Trying model: ...` / `Model in use: ...` in light grey during the run and the final model afterwards.

## 6. Configuration (.env)
| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | - | Enables OpenRouter |
| `OPENROUTER_MODELS` | 3 free models | Comma list, tried in order |
| `OPENROUTER_FALLBACK_MODEL` | `openrouter/free` | Generic free router, tried after the specific ones |
| `GROQ_API_KEY` / `GROQ_MODELS` | - / `llama-3.3-70b-versatile` | Groq fallback |
| `OLLAMA_BASE_URL` / `OLLAMA_MODELS` | `http://localhost:11434` / `llama3.1` | Local fallback |
| `MAX_INPUT_CHARS` | 60000 | Input size limit |
| `MAX_REVISIONS` | 2 | Auto-revision attempts |

## 7. Limitations
- Guardrails reduce, but cannot fully eliminate, model errors; the checks catch unsupported URLs, versions,
  identifiers, wording and structure, not every subtle misstatement. Review before submitting.
- Free-tier models are rate-limited and their IDs change; keep `OPENROUTER_MODELS` current.
- PDF export uses built-in fonts (Latin text); other scripts may render as `?`.
- Very large inputs are rejected rather than chunked.
- A single code snippet rarely states a problem statement, team or setup steps; those sections will
  correctly read "Not specified" and appear in the Information Gaps checklist.
