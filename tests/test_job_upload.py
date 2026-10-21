import pytest
from fastapi.testclient import TestClient
from test_resume import make_pdf

from jobagent.api import app
from jobagent.match_schemas import JobCandidate
from jobagent.matching import build_report


@pytest.fixture()
def client():
    with TestClient(app) as client:
        yield client


def test_pasted_job_is_a_manual_candidate_without_invented_metadata(client):
    response = client.post(
        "/jobs/upload",
        data={
            "title": "Python工程师",
            "text": "要求熟悉 Python 和 Docker，有接口开发经验。",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "manual"
    assert data["title"] == "Python工程师"
    assert data["url"] is None
    assert data["company"] == data["city"] == data["salary"] == ""


def test_utf8_txt_upload_preserves_job_text(client):
    text = "岗位职责：开发企业知识库。要求熟悉 Python、RAG。"
    response = client.post(
        "/jobs/upload",
        files={
            "file": ("jd.txt", text.encode("utf-8-sig"), "text/plain"),
        },
    )
    assert response.status_code == 200
    assert response.json()["raw_text"] == text
    assert response.json()["title"] == "自定义岗位"


def test_pdf_upload_extracts_text_and_uses_optional_title(client):
    response = client.post(
        "/jobs/upload",
        data={"title": "Backend developer"},
        files={
            "file": (
                "jd.pdf",
                make_pdf("Python developer. Requirements: Python and Docker."),
                "application/pdf",
            ),
        },
    )
    assert response.status_code == 200
    assert "Requirements: Python and Docker." in response.json()["raw_text"]
    assert response.json()["title"] == "Backend developer"


@pytest.mark.parametrize(
    "filename,content,reason",
    [
        ("jd.docx", b"document", "仅支持 PDF 或 TXT"),
        ("jd.txt", b"\xff\xfe", "UTF-8"),
        ("jd.pdf", b"invalid pdf", "无法读取招聘 PDF"),
        ("jd.txt", b"short", "过短"),
    ],
)
def test_bad_upload_has_readable_error(client, filename, content, reason):
    response = client.post("/jobs/upload", files={"file": (filename, content)})
    assert response.status_code == 422
    assert reason in response.json()["detail"]
    assert "Traceback" not in response.text


def test_file_and_pasted_text_cannot_silently_override_each_other(client):
    response = client.post(
        "/jobs/upload",
        data={"text": "Another job description"},
        files={
            "file": ("jd.txt", b"Python developer with Docker experience"),
        },
    )
    assert response.status_code == 422
    assert "请选择其中一种" in response.json()["detail"]


def test_manual_job_uses_existing_match_rubric(client, match_request, match_analysis):
    response = client.post("/jobs/upload", data={"text": match_request.job.raw_text})
    match_request.job = JobCandidate.model_validate(response.json())
    report = build_report(match_request, match_analysis, "test-model")
    assert report.total_score == 58.33
    assert report.skill_gaps == ["kubernetes"]


def test_empty_input_is_reported(client):
    response = client.post("/jobs/upload")
    assert response.status_code == 422
    assert "过短" in response.json()["detail"]
