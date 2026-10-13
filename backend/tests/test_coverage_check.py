import shutil
import subprocess
import sys

from app.analyzer import extract_functions
from app.coverage_check import map_function_coverage, prepare_python, run_coverage
from app.coverage_check.runner import coverage_label


def _logs():
    out = []
    return out, (lambda level, msg: out.append((level, msg)))


def test_sample_repo_baseline(sample_repo, tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    cov = run_coverage(sample_repo, job, sys.executable, "before", timeout=120)
    assert cov.ok and cov.pytest_returncode == 0
    # matches a manual `coverage report` on the same data
    manual = subprocess.run(
        [sys.executable, "-m", "coverage", "report", "--format=total", "--precision=2",
         f"--rcfile={job / '.coveragerc'}", f"--data-file={job / '.coverage_before'}"],
        cwd=sample_repo, capture_output=True, text=True,
    )
    assert abs(float(manual.stdout.strip()) - cov.total_pct) < 0.01
    assert 40 <= cov.total_pct <= 50
    per = map_function_coverage(extract_functions(sample_repo).functions, cov)
    assert per["billing.py::tax_for"]["pct"] == 100.0
    assert per["billing.py::apply_coupon"]["pct"] == 0.0
    assert per["billing.py::apply_coupon"]["statements"] == 3
    assert per["cart.py::Cart.add_item"] == {"pct": 87.5, "covered": 7, "statements": 8}
    assert per["cart.py::Cart.cart_total"]["pct"] == 75.0
    assert set(cov.files) == {"billing.py", "cart.py", "checkout.py", "utils.py"}


def test_repo_without_tests(sample_repo_nogit, tmp_path):
    shutil.rmtree(sample_repo_nogit / "tests")
    job = tmp_path / "job"
    job.mkdir()
    cov = run_coverage(sample_repo_nogit, job, sys.executable, "before", timeout=120)
    assert cov.ok
    assert cov.total_pct == 0.0
    assert set(cov.files) == {"billing.py", "cart.py", "checkout.py", "utils.py"}  # never imported -> 0%
    per = map_function_coverage(extract_functions(sample_repo_nogit).functions, cov)
    assert all(v["pct"] == 0.0 for v in per.values())


def test_coverage_labels():
    assert coverage_label(0, 60) == "untested"
    assert coverage_label(30, 60) == "partial"
    assert coverage_label(60, 60) == "tested"


def test_prepare_python_without_requirements(tmp_path):
    logs, log = _logs()
    assert prepare_python(tmp_path, tmp_path, 10, log) == sys.executable
    (tmp_path / "requirements.txt").write_text("# nothing\n")
    assert prepare_python(tmp_path, tmp_path, 10, log) == sys.executable
    assert len(logs) == 2


def test_prepare_python_failed_install_is_non_fatal(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "requirements.txt").write_text("this-package-does-not-exist-smarttest==9.9.9\n")
    logs, log = _logs()
    py = prepare_python(repo, tmp_path, 60, log)
    assert py  # still returns an interpreter
    assert any(level == "warn" for level, _ in logs)
    out = subprocess.run([py, "-c", "import pytest, coverage; print('ok')"], capture_output=True, text=True)
    assert out.stdout.strip() == "ok"  # job venv can still see the backend's pytest/coverage
