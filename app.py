"""Streamlit UI: upload -> agent drafts -> user edits -> export PDF / Markdown."""
from __future__ import annotations

import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from docgen.config import model_chain
from docgen.exporters import slugify, title_of, to_markdown, to_pdf
from docgen.graph import run_pipeline
from docgen.llm import AllModelsFailed, FallbackLLM
from docgen.validators import SNIPPET_LANGUAGES, InputError, validate_file, validate_snippet

st.set_page_config(page_title="Hackathon Doc Agent", page_icon="📄", layout="wide")

st.markdown(
    """
<style>
.block-container { padding-top: 2rem; padding-bottom: 9rem; max-width: 1350px; }
.model-note { color:#9aa0a6; font-size:.82rem; margin:.15rem 0 0 0; }
.stage-note { color:#4f46e5; font-weight:600; }
.hero h1 { margin-bottom:0; }
.hero p { color:#6b7280; margin-top:.2rem; }
/* bottom-right generate bar */
.st-key-genbar { position:fixed; bottom:22px; right:28px; z-index:1000; width:320px;
  background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:14px 16px 10px;
  box-shadow:0 8px 28px rgba(31,36,48,.16); }
.st-key-genbar p { margin-bottom:.2rem; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<div class="hero"><h1>📄 Hackathon Doc Agent</h1>'
            "<p>Turn a code snippet, JSON or YAML file into grounded hackathon documentation. "
            "Nothing is assumed - gaps are flagged, not filled.</p></div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ sidebar
chain = model_chain()
with st.sidebar:
    st.subheader("Model fallback order")
    if chain:
        for n, spec in enumerate(chain, 1):
            st.markdown(f"<div class='model-note'>{n}. {spec.label}</div>", unsafe_allow_html=True)
    st.caption("Set keys in `.env` (see `.env.example`). Providers without a key are skipped.")
    st.subheader("Guardrails")
    st.caption("• Input must be a code snippet, JSON or YAML (validated)\n\n• Secrets redacted before any model call\n\n"
               "• Source treated as data (prompt-injection safe)\n\n• Facts-only prompt, temperature 0\n\n"
               "• Output checked: sections, evidence, URLs, versions, identifiers\n\n• Auto-revision, then flagged if still failing")

# -------------------------------------------------------------------- input
st.session_state.setdefault("doc_text", "")
st.session_state.setdefault("report", None)
st.session_state.setdefault("warnings", [])

mode = st.radio("Input type", ["Code Snippet", "JSON File", "YAML File"], horizontal=True)
snippet, lang, upload = "", "Other", None
if mode == "Code Snippet":
    lang = st.selectbox("Language", SNIPPET_LANGUAGES)
    snippet = st.text_area("Paste your code", height=260, placeholder="Paste a code snippet here…")
elif mode == "JSON File":
    upload = st.file_uploader("Upload a .json file", type=["json"])
else:
    upload = st.file_uploader("Upload a .yaml / .yml file", type=["yaml", "yml"])

run = st.button("Analyze & draft document", type="primary", disabled=not chain)
if not chain:
    st.warning("No model available. Add an API key to `.env` or start Ollama.")

if run:
    try:
        if mode == "Code Snippet":
            vi = validate_snippet(snippet, lang)
        else:
            if upload is None:
                raise InputError("Please upload a file first.")
            vi = validate_file(upload.name, upload.getvalue(), "json" if mode == "JSON File" else "yaml")
    except InputError as e:
        st.error(f"Input rejected: {e}")
        st.stop()

    ctx = get_script_run_ctx()
    stage_ph, model_ph = st.empty(), st.empty()

    def _bind():  # let LangGraph worker threads update Streamlit placeholders
        add_script_run_ctx(threading.current_thread(), ctx)

    def on_stage(msg: str):
        _bind()
        stage_ph.markdown(f"<span class='stage-note'>⏳ {msg}…</span>", unsafe_allow_html=True)

    def on_model(kind, spec, err):
        _bind()
        text = {"trying": f"Trying model: {spec.label}", "using": f"Model in use: {spec.label}",
                "failed": f"{spec.label} unavailable - switching to next model"}[kind]
        model_ph.markdown(f"<div class='model-note'>{text}</div>", unsafe_allow_html=True)

    try:
        result = run_pipeline(vi, FallbackLLM(chain, on_model), on_stage)
    except AllModelsFailed as e:
        stage_ph.empty(); model_ph.empty()
        st.error("Every configured model failed.")
        st.code(str(e))
        st.stop()
    stage_ph.empty(); model_ph.empty()
    st.session_state.doc_text = result["final"]  # set BEFORE the editor widget is created
    st.session_state.report = result["report"]
    st.session_state.warnings = vi.warnings

# ------------------------------------------------------------ editor / view
if st.session_state.doc_text:
    rep = st.session_state.report or {}
    for w in st.session_state.warnings:
        st.warning(w)
    if rep.get("passed"):
        st.success("All guardrail checks passed.")
    else:
        st.warning("Guardrail checks still flagged items after auto-revision. Review before exporting:")
        for issue in rep.get("issues_remaining", []):
            st.markdown(f"- {issue}")
    st.markdown(f"<div class='model-note'>Generated with {rep.get('model_used', 'n/a')} · "
                f"{rep.get('revisions', 0)} revision(s)</div>", unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("✏️ Edit")
        st.text_area("Markdown source", key="doc_text", height=640, label_visibility="collapsed")
    with right:
        st.subheader("👁 Preview")
        with st.container(height=640, border=True):
            st.markdown(st.session_state.doc_text)

    # ---- bottom-right export bar
    with st.container(key="genbar"):
        fmt = st.radio("Export format", ["PDF", "Markdown"], horizontal=True)
        name = slugify(title_of(st.session_state.doc_text))
        if fmt == "PDF":
            data, fname, mime = to_pdf(st.session_state.doc_text), f"{name}.pdf", "application/pdf"
        else:
            data, fname, mime = to_markdown(st.session_state.doc_text), f"{name}.md", "text/markdown"
        st.download_button(f"⬇ Generate {fmt}", data=data, file_name=fname, mime=mime,
                           type="primary", use_container_width=True)
