"""Markdown / PDF export of the (user-edited) document."""
from __future__ import annotations

import io
import re
from xml.sax.saxutils import escape


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "documentation"


def title_of(md: str) -> str:
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else "Project Documentation"


def to_markdown(md: str) -> bytes:
    return md.encode("utf-8")


def _cp(text: str) -> str:  # built-in PDF fonts are cp1252
    return text.encode("cp1252", "replace").decode("cp1252")


def _inline(text: str) -> str:
    t = escape(_cp(text))
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#b3261e">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])_([^_]+)_(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<i>\1</i>", t)
    return t


def to_pdf(md: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle

    title = _cp(title_of(md))
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=10, leading=14.5, alignment=TA_LEFT, spaceAfter=5)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11, spaceAfter=0)
    h = {
        1: ParagraphStyle("h1", parent=ss["Title"], fontSize=22, leading=27, textColor=colors.HexColor("#1f2430"), alignment=TA_LEFT, spaceAfter=10),
        2: ParagraphStyle("h2", parent=ss["Heading2"], fontSize=14, leading=18, textColor=colors.HexColor("#4f46e5"), spaceBefore=14, spaceAfter=6),
        3: ParagraphStyle("h3", parent=ss["Heading3"], fontSize=11.5, leading=15, textColor=colors.HexColor("#1f2430"), spaceBefore=8, spaceAfter=4),
    }
    quote = ParagraphStyle("quote", parent=body, leftIndent=10, textColor=colors.HexColor("#555b6e"))
    code = ParagraphStyle("code", parent=ss["Code"], fontSize=8, leading=10.5, backColor=colors.HexColor("#f3f4f8"),
                          borderPadding=5, leftIndent=4, spaceBefore=4, spaceAfter=8)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            bottomMargin=20 * mm, title=title, author="Hackathon Doc Agent")

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#8a8fa3"))
        canvas.drawString(20 * mm, 12 * mm, title[:80])
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {d.page}")
        canvas.restoreState()

    story, lines, i = [], md.splitlines(), 0
    para: list[str] = []

    def flush():
        if para:
            story.append(Paragraph(_inline(" ".join(para)), body))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("```"):
            flush()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                raw = _cp(lines[i].replace("\t", "    "))
                block += [raw[j:j + 92] for j in range(0, max(len(raw), 1), 92)]
                i += 1
            story.append(Preformatted("\n".join(block), code))
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            i -= 1
            n = max(len(r) for r in rows)
            data = [[Paragraph(_inline(c), small) for c in r + [""] * (n - len(r))] for r in rows]
            t = Table(data, colWidths=[doc.width / n] * n, repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd3e0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eceefb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [t, Spacer(1, 8)]
        elif (m := re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", ln)):
            flush()
            story.append(Paragraph(_inline(m.group(2)), h[min(len(m.group(1)), 3)]))
        elif (m := re.match(r"^(\s*)[-*+]\s+(.*)$", ln)):
            flush()
            indent = 12 + 12 * (len(m.group(1)) // 2)
            story.append(Paragraph(_inline(m.group(2)), ParagraphStyle("b", parent=body, leftIndent=indent, bulletIndent=indent - 10, spaceAfter=2), bulletText="\u2022"))
        elif (m := re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", ln)):
            flush()
            story.append(Paragraph(_inline(m.group(3)), ParagraphStyle("n", parent=body, leftIndent=16, bulletIndent=0, spaceAfter=2), bulletText=f"{m.group(2)}."))
        elif s.startswith(">"):
            flush()
            story.append(Paragraph(_inline(s.lstrip("> ").strip()), quote))
        elif re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", s):
            flush()
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cfd3e0"), spaceBefore=6, spaceAfter=6))
        elif not s:
            flush()
        else:
            para.append(s)
        i += 1
    flush()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
