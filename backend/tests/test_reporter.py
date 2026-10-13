from app.reporter import build_pdf, build_summary
from app.reporter.pdf import clean

JOB = {"job_id": "abc123", "project_name": "shop \u2192 demo", "llm_provider": "mock",
       "settings": {"model": "qwen2.5-coder:7b", "coverage_threshold": 60, "max_functions": 10},
       "coverage_before": 45.0, "coverage_after": 70.0, "newly_covered": ["billing.py::apply_coupon"]}

BUG_TEST = {"name": "test_apply_coupon_at_minimum_boundary", "status": "possible_bug", "code": "...", "attempts": 1,
            "reason": "Expected 45.0, function returned 50", "expected": "45.0", "actual": "50", "traceback": "E",
            "verdict": {"verdict": "likely_bug", "reason": "uses > instead of >= \u2014 boundary excluded"}}


def _fn(fid, status, tests, candidate=True, after=100.0):
    file, q = fid.split("::")
    return {"id": fid, "file": file, "qualname": q, "line_start": 3, "line_end": 9, "candidate": candidate,
            "processed": bool(tests), "status": status, "tests": tests, "coverage_pct": 0.0, "rank": 1,
            "coverage_after_pct": after, "last_modified_days": 2, "usage_count": 3, "risk_score": 0.9,
            "risk_label": "High"}


FUNCS = [
    _fn("billing.py::apply_coupon", "possible_bug",
        [BUG_TEST, {**BUG_TEST, "name": "test_ok", "status": "accepted", "verdict": None}]),
    _fn("cart.py::Cart.remove_item", "rejected", [{**BUG_TEST, "name": "t", "status": "rejected", "verdict": None}],
        after=0.0),
    _fn("utils.py::slugify", "pending", [], candidate=False),
]


def test_build_summary_counts():
    s = build_summary(JOB, FUNCS)
    assert s["coverage_delta"] == 25.0
    assert (s["tests_generated"], s["accepted"], s["rejected"], s["possible_bugs"]) == (3, 1, 1, 1)
    assert s["untested_before"] == 2 and s["untested_after"] == 1
    assert s["functions_processed"] == 2
    assert s["bugs"][0]["reason"].startswith("uses > instead of >=")
    assert s["newly_covered"] == ["billing.py::apply_coupon"]


def test_build_summary_before_generation():
    s = build_summary({**JOB, "coverage_after": None}, FUNCS)
    assert s["generated"] is False and s["coverage_delta"] is None and s["untested_after"] is None


def test_pdf_contains_every_section():
    import io

    from pypdf import PdfReader

    data = build_pdf(JOB, FUNCS, build_summary(JOB, FUNCS))
    assert data.startswith(b"%PDF")
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
    for needle in ["SmartTest Report", "shop -> demo", "Model used: mock", "Summary", "Coverage before", "45.0%",
                   "Priority list", "Per-function results", "POSSIBLE BUG FOUND", "Possible bugs",
                   "billing.py:3-9", "test_apply_coupon_at_minimum_boundary", "Limitations", "AI-generated"]:
        assert needle in text, needle


def test_clean_only_latin1():
    assert clean("a \u2192 b <c> \U0001F41B") == "a -&gt; b &lt;c&gt; ?"
