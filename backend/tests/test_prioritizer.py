import os
import time

from app.analyzer import count_calls, extract_functions, find_call_sites
from app.prioritizer import last_change_days, prioritize, risk_label
from app.prioritizer.risk import open_repo


def _rank(repo):
    res = extract_functions(repo)
    sites = find_call_sites(repo, res.trees)
    usage = {f["id"]: count_calls(f, sites) for f in res.functions}
    return prioritize(repo, res.functions, usage)


def test_recent_and_used_rank_above_old_unused(sample_repo):
    ranked, used_git = _rank(sample_repo)
    assert used_git
    ids = [f["id"] for f in ranked]
    scores = {f["id"]: f for f in ranked}
    assert ids[0] == "billing.py::apply_coupon"
    assert scores["billing.py::apply_coupon"]["risk_label"] == "High"
    assert scores["billing.py::apply_coupon"]["last_modified_days"] <= 3
    assert scores["utils.py::chunk_list"]["risk_label"] == "Low"
    assert scores["utils.py::chunk_list"]["last_modified_days"] >= 140
    assert ids.index("billing.py::apply_coupon") < ids.index("utils.py::chunk_list")
    assert ids.index("billing.py::calculate_discount") < ids.index("cart.py::Cart.remove_item")
    assert all(0 <= f["risk_score"] <= 1 for f in ranked)
    assert [f["risk_score"] for f in ranked] == sorted([f["risk_score"] for f in ranked], reverse=True)


def test_blame_uses_newest_line(sample_repo):
    repo = open_repo(sample_repo)
    fn = next(f for f in extract_functions(sample_repo).functions if f["id"] == "billing.py::tax_for")
    days, source = last_change_days(sample_repo, fn, repo)
    assert source == "git" and 115 <= days <= 125


def test_works_without_git_history(sample_repo_nogit):
    old = time.time() - 90 * 86400
    os.utime(sample_repo_nogit / "utils.py", (old, old))
    ranked, used_git = _rank(sample_repo_nogit)
    assert not used_git
    by_id = {f["id"]: f for f in ranked}
    assert by_id["utils.py::chunk_list"]["last_modified_days"] >= 89
    assert by_id["billing.py::apply_coupon"]["last_modified_days"] == 0
    assert ranked[0]["id"] in {"billing.py::apply_coupon", "billing.py::calculate_discount", "cart.py::Cart.cart_total"}


def test_risk_formula_and_labels(tmp_path):
    (tmp_path / "m.py").write_text("def a():\n    return 1\n\ndef b():\n    return a() + a()\n")
    res = extract_functions(tmp_path)
    usage = {"m.py::a": 4, "m.py::b": 0}
    ranked, _ = prioritize(tmp_path, res.functions, usage, now=time.time())
    a = next(f for f in ranked if f["name"] == "a")
    b = next(f for f in ranked if f["name"] == "b")
    assert a["risk_score"] == 1.0 and a["risk_label"] == "High"
    assert b["risk_score"] == 0.5 and b["risk_label"] == "Medium"
    assert risk_label(0.66) == "High" and risk_label(0.33) == "Medium" and risk_label(0.32) == "Low"


def test_no_usage_anywhere(tmp_path):
    (tmp_path / "m.py").write_text("def a():\n    return 1\n")
    ranked, _ = prioritize(tmp_path, extract_functions(tmp_path).functions, {})
    assert ranked[0]["usage_count"] == 0 and ranked[0]["risk_score"] == 0.5
