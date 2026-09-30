"""LangGraph pipeline:

    load_skill -> analyze -> draft -> guard --(issues & retries left)--> revise -> guard
                                        \\--(clean or out of retries)--> finalize
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from .config import MAX_REVISIONS
from .guardrails import check_output, number_lines, sanitize_output
from .prompts import ANALYZE_PROMPT, DRAFT_PROMPT, REVISE_PROMPT, SYSTEM_RULES
from .skill_loader import load_skill
from .validators import ValidatedInput

StageCb = Callable[[str], None]


class DocState(TypedDict, total=False):
    kind: str
    filename: str
    content: str
    numbered: str
    skill: Any
    facts: str
    draft: str
    issues: list[str]
    attempts: int
    final: str
    report: dict


def build_graph(llm, on_stage: Optional[StageCb] = None, max_revisions: int = MAX_REVISIONS):
    """`llm` is any object with `.invoke(messages) -> str` (see llm.FallbackLLM)."""

    def stage(msg: str) -> None:
        if on_stage:
            try:
                on_stage(msg)
            except Exception:
                pass

    def system(state: DocState) -> SystemMessage:
        return SystemMessage(content=SYSTEM_RULES + "\n\n" + state["skill"].prompt)

    def n_load_skill(state: DocState):
        stage("Loading documentation skill")
        return {"skill": load_skill(), "numbered": number_lines(state["content"]), "attempts": 0}

    def n_analyze(state: DocState):
        stage("Extracting facts from the input")
        prompt = ANALYZE_PROMPT.format(kind=state["kind"], filename=state["filename"], numbered=state["numbered"])
        return {"facts": llm.invoke([system(state), HumanMessage(content=prompt)])}

    def n_draft(state: DocState):
        stage("Drafting the document")
        prompt = DRAFT_PROMPT.format(
            facts=state["facts"], kind=state["kind"], filename=state["filename"], numbered=state["numbered"]
        )
        return {"draft": sanitize_output(llm.invoke([system(state), HumanMessage(content=prompt)]))}

    def n_guard(state: DocState):
        stage("Running guardrail checks")
        return {"issues": check_output(state["draft"], state["content"], state["skill"].sections)}

    def route(state: DocState) -> str:
        return "revise" if state["issues"] and state["attempts"] < max_revisions else "finalize"

    def n_revise(state: DocState):
        attempt = state["attempts"] + 1
        stage(f"Revising draft (attempt {attempt}/{max_revisions})")
        prompt = REVISE_PROMPT.format(
            issues="\n".join(f"- {i}" for i in state["issues"]),
            draft=state["draft"],
            kind=state["kind"],
            filename=state["filename"],
            numbered=state["numbered"],
        )
        text = llm.invoke([system(state), HumanMessage(content=prompt)])
        return {"draft": sanitize_output(text), "attempts": attempt}

    def n_finalize(state: DocState):
        stage("Finalizing")
        digest = hashlib.sha256(state["content"].encode()).hexdigest()[:12]
        model = getattr(llm, "last_label", "unknown")
        footer = f"\n\n---\n_Generated from `{state['filename']}` ({state['kind']}, sha256 {digest}) using {model}._\n"
        return {
            "final": state["draft"].rstrip() + footer,
            "report": {
                "model_used": model,
                "revisions": state["attempts"],
                "issues_remaining": state["issues"],
                "passed": not state["issues"],
            },
        }

    g = StateGraph(DocState)
    g.add_node("load_skill", n_load_skill)
    g.add_node("analyze", n_analyze)
    g.add_node("draft", n_draft)
    g.add_node("guard", n_guard)
    g.add_node("revise", n_revise)
    g.add_node("finalize", n_finalize)
    g.add_edge(START, "load_skill")
    g.add_edge("load_skill", "analyze")
    g.add_edge("analyze", "draft")
    g.add_edge("draft", "guard")
    g.add_conditional_edges("guard", route, {"revise": "revise", "finalize": "finalize"})
    g.add_edge("revise", "guard")
    g.add_edge("finalize", END)
    return g.compile()


def run_pipeline(vi: ValidatedInput, llm, on_stage: Optional[StageCb] = None) -> DocState:
    graph = build_graph(llm, on_stage)
    return graph.invoke({"kind": vi.kind, "filename": vi.filename, "content": vi.content})
