"""Build summary.json (section 7) from the job's function records."""
from __future__ import annotations

COUNTED = ("accepted", "needs_review", "rejected", "possible_bug")


def build_summary(job: dict, functions: list[dict]) -> dict:
    candidates = [f for f in functions if f.get("candidate")]
    processed = [f for f in functions if f.get("processed")]
    tests = [t for f in processed for t in f.get("tests", [])]
    counts = {k: sum(1 for t in tests if t.get("status") == k) for k in COUNTED}
    before = job.get("coverage_before")
    after = job.get("coverage_after")
    generated = after is not None
    threshold = job.get("settings", {}).get("coverage_threshold", 60)
    untested_after = None
    if generated:
        untested_after = sum(
            1 for f in candidates
            if (f.get("coverage_after_pct") if f.get("coverage_after_pct") is not None else f["coverage_pct"])
            < threshold
        )
    bugs = []
    for f in processed:
        for t in f.get("tests", []):
            if t.get("status") == "possible_bug":
                bugs.append({
                    "function_id": f["id"],
                    "file": f["file"],
                    "line_start": f["line_start"],
                    "line_end": f["line_end"],
                    "qualname": f["qualname"],
                    "test": t["name"],
                    "expected": t.get("expected"),
                    "actual": t.get("actual"),
                    "reason": (t.get("verdict") or {}).get("reason") or t.get("reason", ""),
                })
    return {
        "project_name": job.get("project_name"),
        "model": job.get("model_used") or job.get("settings", {}).get("model"),
        "generated": generated,
        "coverage_before": before,
        "coverage_after": after,
        "coverage_delta": round(after - before, 2) if generated and before is not None else None,
        "untested_before": len(candidates),
        "untested_after": untested_after,
        "functions_total": len(functions),
        "functions_processed": len(processed),
        "tests_generated": len(tests),
        "accepted": counts["accepted"],
        "needs_review": counts["needs_review"],
        "rejected": counts["rejected"],
        "possible_bugs": counts["possible_bug"],
        "newly_covered": job.get("newly_covered", []),
        "bugs": bugs,
    }
