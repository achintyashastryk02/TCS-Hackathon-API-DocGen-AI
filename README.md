# Hackathon Doc Agent

A LangChain + LangGraph agent with a Streamlit UI. Upload a **code snippet, JSON file or YAML file**;
the agent drafts hackathon documentation that contains **only what is in your input**, lets you
**edit it**, then exports **PDF or Markdown** (button at the bottom right).

## Quick start (uv)

```bash
uv sync                      # installs everything from pyproject.toml
cp .env.example .env         # add OPENROUTER_API_KEY and/or GROQ_API_KEY (Ollama needs none)
uv run streamlit run app.py
```

Run tests: `uv run pytest`

## Model fallback order
OpenRouter (up to 3 specific `:free` models, then `openrouter/free`) -> Groq -> Ollama.
The model currently being tried is shown in light grey text while loading.

See **STEPS.md** (build/run/extend steps) and **DOCS.md** (architecture, guardrails, config reference).
