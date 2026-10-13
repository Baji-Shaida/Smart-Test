"""End-to-end: sample repo zip -> analysis -> generation (mock LLM) -> summary, PDF and accepted-tests zip."""
import io
import shutil
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.jobs import reset_manager
from app.main import app


@pytest.fixture()
def client(tmp_path):
    reset_manager(tmp_path / "jobs")
    with TestClient(app) as c:
        yield c


def _wait(client, job_id, statuses, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["status"] in statuses:
            return state
        time.sleep(0.2)
    raise AssertionError(f"job stuck: {state}")


def test_sample_repo_end_to_end(client, sample_repo, tmp_path):
    assert client.get("/api/health").json()["llm_provider"] == "mock"
    archive = shutil.make_archive(str(tmp_path / "sample_repo"), "zip", root_dir=sample_repo.parent,
                                  base_dir=sample_repo.name)
    with open(archive, "rb") as fh:
        r = client.post("/api/jobs", files={"file": ("sample_repo.zip", fh, "application/zip")},
                        data={"settings": '{"max_functions": 10, "coverage_threshold": 60}'})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]

    state = _wait(client, job_id, {"analyzed", "failed"})
    assert state["status"] == "analyzed", state.get("error")
    assert 40 <= state["coverage_before"] <= 50
    candidates = [f for f in client.get(f"/api/jobs/{job_id}/functions").json() if f["candidate"]]
    assert candidates[0]["qualname"] == "apply_coupon" and candidates[0]["risk_label"] == "High"

    assert client.post(f"/api/jobs/{job_id}/generate", json={"all": True}).status_code == 202
    state = _wait(client, job_id, {"completed", "failed"})
    assert state["status"] == "completed", state.get("error")

    events = client.get(f"/api/jobs/{job_id}/events").text
    for name in ("analysis_complete", "function_update", "generation_complete"):
        assert f"event: {name}" in events

    by_name = {f["qualname"]: f for f in client.get(f"/api/jobs/{job_id}/functions").json()}
    statuses = {f["status"] for f in by_name.values() if f["processed"]}
    assert {"accepted", "rejected", "possible_bug"} <= statuses
    assert by_name["apply_coupon"]["status"] == "possible_bug"
    assert by_name["Cart.remove_item"]["status"] == "rejected"
    assert by_name["calculate_discount"]["status"] == "accepted"
    detail = client.get(f"/api/jobs/{job_id}/functions/billing.py::apply_coupon").json()
    bug = next(t for t in detail["tests"] if t["status"] == "possible_bug")
    assert bug["verdict"]["verdict"] == "likely_bug" and bug["expected"] and bug["actual"]
    assert detail["source"].lstrip().startswith("def apply_coupon")

    summary = client.get(f"/api/jobs/{job_id}/summary").json()
    assert summary["coverage_after"] > summary["coverage_before"]
    assert summary["untested_after"] < summary["untested_before"]
    assert summary["possible_bugs"] >= 1 and summary["accepted"] >= 1
    assert any(b["qualname"] == "apply_coupon" for b in summary["bugs"])

    pdf = client.get(f"/api/jobs/{job_id}/report.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    for needle in ("SmartTest Report", "sample_repo", "Priority list", "Per-function results", "Possible bugs",
                   "apply_coupon", "Limitations"):
        assert needle in text

    z = client.get(f"/api/jobs/{job_id}/tests.zip")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert names and all(n.startswith("accepted_tests/test_") for n in names)
    assert not any("remove_item" in n for n in names)
    content = zipfile.ZipFile(io.BytesIO(z.content)).read("accepted_tests/test_billing__apply_coupon.py").decode()
    assert "at_minimum_boundary" not in content
