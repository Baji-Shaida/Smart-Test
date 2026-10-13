"""PDF report (reportlab, standard Helvetica/Courier fonts only)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STATUS_TEXT = {
    "accepted": "ACCEPTED",
    "needs_review": "NEEDS REVIEW",
    "rejected": "REJECTED",
    "possible_bug": "POSSIBLE BUG FOUND",
    "pending": "PENDING",
    "generating": "GENERATING",
}
STATUS_COLOR = {
    "accepted": colors.HexColor("#047857"),
    "possible_bug": colors.HexColor("#c2410c"),
    "needs_review": colors.HexColor("#a16207"),
    "rejected": colors.HexColor("#475569"),
}
REPLACEMENTS = {"\u2192": "->", "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"',
                "\u201d": '"', "\u2026": "...", "\u2265": ">=", "\u2264": "<=", "\u00d7": "x"}
LIMITATIONS = [
    "Tests are AI-generated and must be reviewed by a human before you rely on them.",
    "The LLM infers intent from code and docstrings; it cannot know what the developer meant. Poorly named or "
    "undocumented functions yield weaker tests.",
    "Possible Bug Found means 'worth a human look', not proof of a bug.",
    "Static analysis and subprocess runs do not reproduce every runtime condition (network, concurrency, "
    "external services).",
    "Functions needing complex fixtures or external services may be Rejected or Needs Review.",
]


def clean(value) -> str:
    """Escape for Paragraph markup and keep only characters the standard PDF fonts can render."""
    text = "" if value is None else str(value)
    for k, v in REPLACEMENTS.items():
        text = text.replace(k, v)
    text = text.encode("latin-1", "replace").decode("latin-1")
    return escape(text)


def _pct(v) -> str:
    return "-" if v is None else f"{v:.1f}%"


def _table(rows, widths, header_bg="#e0e7ff"):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    return t


def build_pdf(job: dict, functions: list[dict], summary: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=15 * mm, title="SmartTest Report", author="SmartTest")
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)
    mono = ParagraphStyle("mono", parent=cell, fontName="Courier", fontSize=7.5, leading=9.5)
    h1, h2 = ss["Title"], ss["Heading2"]
    P = lambda t, st=cell: Paragraph(t, st)  # noqa: E731

    model = job.get("model_used") or ("mock" if job.get("llm_provider") == "mock" else job["settings"]["model"])
    story = [
        Paragraph("SmartTest Report", h1),
        Paragraph(f"<b>Project:</b> {clean(job.get('project_name'))}", body),
        Paragraph(f"<b>Date:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", body),
        Paragraph(f"<b>Model used:</b> {clean(model)}", body),
        Paragraph(f"<b>Coverage threshold:</b> {job['settings']['coverage_threshold']:g}%  "
                  f"<b>Job:</b> {clean(job['job_id'])}", body),
        Spacer(1, 6 * mm),
        Paragraph("Summary", h2),
    ]
    s = summary
    delta = s.get("coverage_delta")
    rows = [
        ["Metric", "Value"],
        ["Coverage before", _pct(s.get("coverage_before"))],
        ["Coverage after", _pct(s.get("coverage_after"))],
        ["Coverage delta", "-" if delta is None else f"{delta:+.1f}%"],
        ["Untested functions before", str(s.get("untested_before"))],
        ["Untested functions after", "-" if s.get("untested_after") is None else str(s["untested_after"])],
        ["Functions processed", str(s.get("functions_processed"))],
        ["Tests generated", str(s.get("tests_generated"))],
        ["Accepted", str(s.get("accepted"))],
        ["Needs review", str(s.get("needs_review"))],
        ["Rejected", str(s.get("rejected"))],
        ["Possible bugs found", str(s.get("possible_bugs"))],
    ]
    story += [_table(rows, [70 * mm, 50 * mm]), Spacer(1, 6 * mm)]

    candidates = [f for f in functions if f.get("candidate")]
    story.append(Paragraph("Priority list (ranked by risk)", h2))
    if candidates:
        rows = [["#", "Function", "File", "Coverage", "Last change", "Usage", "Risk"]]
        for f in candidates:
            rows.append([str(f.get("rank", "")), P(clean(f["qualname"])), P(clean(f["file"])),
                         f"{f['coverage_pct']:.0f}%", f"{f.get('last_modified_days', '-')}d",
                         str(f.get("usage_count", 0)), f"{f.get('risk_label')} ({f.get('risk_score', 0):.2f})"])
        story.append(_table(rows, [8 * mm, 45 * mm, 40 * mm, 18 * mm, 20 * mm, 14 * mm, 35 * mm]))
    else:
        story.append(Paragraph("No functions were below the coverage threshold.", body))
    story.append(Spacer(1, 6 * mm))

    processed = [f for f in functions if f.get("processed")]
    story.append(Paragraph("Per-function results", h2))
    if processed:
        rows = [["Function", "Status", "Tests (acc/review/rej/bug)", "Coverage", "Notes"]]
        for f in processed:
            tests = f.get("tests", [])
            c = {k: sum(1 for t in tests if t["status"] == k) for k in STATUS_COLOR}
            status = f.get("status", "pending")
            color = STATUS_COLOR.get(status, colors.black).hexval()[2:]
            note = f.get("error") or next((t.get("reason") for t in tests if t["status"] != "accepted"), "") or ""
            after = f.get("coverage_after_pct")
            rows.append([
                P(f"{clean(f['qualname'])}<br/><font color='#64748b'>{clean(f['file'])}</font>"),
                P(f"<font color='#{color}'><b>{STATUS_TEXT.get(status, status)}</b></font>"),
                f"{c['accepted']}/{c['needs_review']}/{c['rejected']}/{c['possible_bug']}",
                f"{f['coverage_pct']:.0f}% -> {'-' if after is None else f'{after:.0f}%'}",
                P(clean(note[:200])),
            ])
        story.append(_table(rows, [42 * mm, 40 * mm, 28 * mm, 22 * mm, 48 * mm]))
    else:
        story.append(Paragraph("No tests have been generated yet.", body))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Possible bugs", h2))
    bugs = s.get("bugs", [])
    if bugs:
        for b in bugs:
            rows = [
                ["Function", P(clean(b["qualname"]))],
                ["File and line", P(f"{clean(b['file'])}:{b['line_start']}-{b['line_end']}")],
                ["Failing test", P(clean(b["test"]), mono)],
                ["Expected", P(clean(b.get("expected")), mono)],
                ["Actual", P(clean(b.get("actual")), mono)],
                ["Reason", P(clean(b.get("reason")))],
            ]
            t = Table(rows, colWidths=[30 * mm, 150 * mm])
            t.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#f97316")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ffedd5")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#fed7aa")),
            ]))
            story += [t, Spacer(1, 4 * mm)]
    else:
        story.append(Paragraph("No possible bugs were found.", body))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Limitations", h2))
    for line in LIMITATIONS:
        story.append(Paragraph(f"- {clean(line)}", body))

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 8 * mm, "SmartTest - AI-generated tests must be reviewed by a human.")
        canvas.drawRightString(A4[0] - 15 * mm, 8 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
