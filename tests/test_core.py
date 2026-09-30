import json
import pytest

from docgen.exporters import to_markdown, to_pdf
from docgen.graph import run_pipeline
from docgen.guardrails import check_output, redact_secrets, sanitize_output
from docgen.skill_loader import load_skill
from docgen.validators import InputError, validate_file, validate_snippet

SKILL = load_skill()


def good_doc(extra=""):
    parts = ["# Demo App\n"]
    for i, s in enumerate(SKILL.sections, 1):
        ev = "" if s.get("evidence", True) is False else "\nEvidence: L1-L3"
        parts.append(f"## {i}. {s['title']}\nNot specified in the provided input. {extra}{ev}\n")
    return "\n".join(parts)


def test_snippet_rules():
    with pytest.raises(InputError):
        validate_snippet("   ")
    with pytest.raises(InputError):
        validate_snippet("def f(:\n  pass", "Python")
    assert validate_snippet("def f():\n    return 1", "Python").kind == "code"


def test_json_yaml_rules():
    with pytest.raises(InputError):
        validate_file("a.json", b"{bad", "json")
    with pytest.raises(InputError):
        validate_file("a.txt", b"{}", "json")
    with pytest.raises(InputError):
        validate_file("a.yaml", b"just a string", "yaml")
    with pytest.raises(InputError):
        validate_file("a.yaml", b"a: [1, 2", "yaml")
    assert validate_file("a.json", json.dumps({"a": 1}).encode(), "json").kind == "json"
    assert validate_file("a.yml", b"a: 1\nb: [1, 2]", "yaml").kind == "yaml"


def test_secret_redaction():
    t, n = redact_secrets('api_key = "abcd1234efgh"\npassword: hunter2abc\nx = 5')
    assert n == 2 and "abcd1234efgh" not in t and "hunter2abc" not in t and "x = 5" in t


def test_guardrails_flag_ungrounded():
    src = "def add(a, b): return a + b"
    assert check_output(good_doc(), src, SKILL.sections) == []
    bad = good_doc("See https://evil.example.com, v9.9.9, `mystery_fn`, cutting-edge.")
    issues = " ".join(check_output(bad, src, SKILL.sections))
    for needle in ("evil.example.com", "9.9.9", "mystery_fn", "cutting-edge"):
        assert needle in issues


def test_missing_section_and_evidence():
    doc = good_doc().replace("Evidence: L1-L3", "", 1)
    assert any("Evidence" in i for i in check_output(doc, "x" * 50, SKILL.sections))
    assert any("Missing required section" in i for i in check_output("# T\n" + "x" * 500, "s", SKILL.sections))


def test_api_documentation_sections_are_required():
    required = {"Endpoint Description", "Parameters", "Setup and Installation", "Usage Examples"}
    excluded = {
        "Usage Instructions",
        "Security and Data Handling",
        "Testing and Validation",
        "Limitations and Known Gaps",
        "Future Scope",
        "Team and Submission Details",
        "Information Gaps",
    }
    titles = {section["title"] for section in SKILL.sections}
    assert required <= titles
    assert not (excluded & titles)
    endpoint_guidance = next(s["guidance"] for s in SKILL.sections if s["title"] == "Endpoint Description")
    example_guidance = next(s["guidance"] for s in SKILL.sections if s["title"] == "Usage Examples")
    assert "response" in endpoint_guidance.lower()
    assert "status code" in endpoint_guidance.lower()
    assert "user's perspective" in example_guidance
    assert "corresponding API response" in example_guidance
    doc = good_doc()
    for title in required:
        section_number = next(i for i, section in enumerate(SKILL.sections, 1) if section["title"] == title)
        assert f"## {section_number}. {title}" in doc
    assert check_output(doc, "def f(): return 1", SKILL.sections) == []


def test_sanitize():
    assert sanitize_output("Sure!\n# T\n<script>x</script>body").startswith("# T")


class FakeLLM:
    last_label = "fake · model"

    def __init__(self, docs):
        self.docs, self.calls = list(docs), 0

    def invoke(self, messages):
        self.calls += 1
        return self.docs.pop(0) if len(self.docs) > 1 else self.docs[0]


def test_pipeline_revises_then_passes():
    vi = validate_snippet("def add(a, b):\n    return a + b", "Python")
    llm = FakeLLM(["facts", good_doc("See https://evil.example.com"), good_doc()])
    out = run_pipeline(vi, llm)
    assert out["report"]["passed"] and out["report"]["revisions"] == 1
    assert "sha256" in out["final"]


def test_pipeline_gives_up_and_reports():
    vi = validate_snippet("def add(a, b):\n    return a + b", "Python")
    out = run_pipeline(vi, FakeLLM(["facts", good_doc("cutting-edge")]))
    assert not out["report"]["passed"] and out["report"]["issues_remaining"]


def test_exports():
    md = good_doc() + "\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint('x')\n```\n- item **bold** `code`\n"
    assert to_pdf(md)[:4] == b"%PDF"
    assert to_markdown("é").decode() == "é"
