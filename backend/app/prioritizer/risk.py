"""Risk-based prioritization: recency of change (git blame) + usage frequency."""
from __future__ import annotations

import time
from pathlib import Path

try:
    import git  # GitPython
except Exception:  # pragma: no cover - git binary missing
    git = None  # type: ignore[assignment]


def open_repo(root: Path):
    """Return a GitPython Repo with at least one commit, or None."""
    if git is None:
        return None
    try:
        repo = git.Repo(str(root), search_parent_directories=False)
        _ = repo.head.commit  # raises if there are no commits
        return repo
    except Exception:  # noqa: BLE001
        return None


def _blame_time(repo, rel: str, start: int, end: int) -> float | None:
    try:
        out = repo.git.blame("-L", f"{start},{end}", "--porcelain", "HEAD", "--", rel)
    except Exception:  # noqa: BLE001
        return None
    times = [int(line.split()[1]) for line in out.splitlines() if line.startswith("committer-time ")]
    return float(max(times)) if times else None


def last_change_days(root: Path, fn: dict, repo=None, now: float | None = None) -> tuple[float, str]:
    """Days since the newest change to any line of ``fn``. Returns (days, source) with source git|mtime."""
    now = now if now is not None else time.time()
    ts = _blame_time(repo, fn["file"], fn["line_start"], fn["line_end"]) if repo is not None else None
    source = "git"
    if ts is None:
        source = "mtime"
        try:
            ts = (Path(root) / fn["file"]).stat().st_mtime
        except OSError:
            ts = now
    return max(0.0, (now - ts) / 86400.0), source


def risk_label(score: float) -> str:
    if score >= 0.66:
        return "High"
    if score >= 0.33:
        return "Medium"
    return "Low"


def prioritize(root: Path, candidates: list[dict], usage_counts: dict[str, int],
               w_recency: float = 0.5, w_usage: float = 0.5, now: float | None = None) -> tuple[list[dict], bool]:
    """Score candidates in place and return (sorted_candidates, used_git_history)."""
    repo = open_repo(Path(root))
    max_calls = max([usage_counts.get(c["id"], 0) for c in candidates] + [0])
    for c in candidates:
        days, _ = last_change_days(root, c, repo, now)
        recency = 1.0 / (1.0 + days / 30.0)
        calls = usage_counts.get(c["id"], 0)
        usage = min(calls / max_calls, 1.0) if max_calls else 0.0
        score = w_recency * recency + w_usage * usage
        c["last_modified_days"] = int(days)
        c["usage_count"] = calls
        c["risk_score"] = round(score, 2)
        c["risk_label"] = risk_label(round(score, 2))
    ranked = sorted(candidates, key=lambda c: (-c["risk_score"], c["last_modified_days"], c["id"]))
    return ranked, repo is not None
