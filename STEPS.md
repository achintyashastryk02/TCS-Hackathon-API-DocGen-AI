# STEPS - build, run and extend

## A. Run it
1. Install uv: https://docs.astral.sh/uv/ (`pip install uv` also works).
2. In the project folder: `uv sync` (creates `.venv`, installs from `pyproject.toml`).
3. `cp .env.example .env` and fill in:
   - `OPENROUTER_API_KEY` (primary) - and check the `:free` model IDs in `OPENROUTER_MODELS`
     are still listed on openrouter.ai (free IDs change often).
   - `GROQ_API_KEY` (second fallback).
   - Ollama: install it, run `ollama pull llama3.1`, keep `ollama serve` running (last fallback).
4. `uv run streamlit run app.py` and open the URL shown (default http://localhost:8501).

## B. Use it
1. Choose the input type: **Code Snippet**, **JSON File** or **YAML File**.
2. Paste the code (pick its language) or upload the file. Invalid input is rejected with the line number.
3. Click **Analyze & draft document**. While it runs you see the current stage and, in light text,
   the model being tried (and any switch to the next model).
4. Read the **guardrail result**. If checks still fail after auto-revision, the issues are listed.
5. Edit the Markdown on the left; the preview on the right updates.
6. Pick **PDF** or **Markdown** in the bottom-right bar and press **Generate**.
   The file is built from your edited text.

## C. Match your hackathon's requirements
1. Open `skills/documentation/sections.yaml` - add, remove or rename sections and their guidance.
   The agent, prompts and guardrail checks all follow this file automatically.
2. Edit `skills/documentation/references/hackathon_requirements.md` with your judging criteria.
3. Edit `skills/documentation/SKILL.md` to change tone or writing rules.

## D. Extend it
- New provider: add a branch in `docgen/llm.py::build_chat_model` and a rule in `docgen/config.py::model_chain`.
- New guardrail: add a check in `docgen/guardrails.py::check_output` (return a string per violation).
- New node (e.g. diagram generation): add it in `docgen/graph.py` and connect the edges.
- More input types: add a validator in `docgen/validators.py` and an option in `app.py`.

## E. Verify
`uv run pytest` covers validators, secret redaction, guardrails, the revise loop and PDF export
(with a fake LLM, so no API keys are needed).
