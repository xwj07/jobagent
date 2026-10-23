"""Size limits: oversized inputs are rejected before any parsing or model call."""

import io
from unittest.mock import Mock

import pytest

from jobagent.job_input import manual_job, read_job_file
from jobagent.uploads import MAX_JOB_TEXT_CHARS, MB, UploadTooLarge, read_limited


def test_read_limited_accepts_exact_limit():
    assert read_limited(io.BytesIO(b"x" * 10), 10, "测试") == b"x" * 10


def test_read_limited_rejects_one_byte_over_without_reading_everything():
    stream = io.BytesIO(b"x" * 1000)
    with pytest.raises(UploadTooLarge) as info:
        read_limited(stream, 10, "测试")
    assert "测试" in str(info.value)
    # Only limit + 1 bytes were consumed, so a giant file is never fully loaded.
    assert stream.tell() == 11


def test_upload_too_large_is_a_value_error_for_existing_handlers():
    assert issubclass(UploadTooLarge, ValueError)


def test_txt_over_limit_is_rejected_before_decoding(monkeypatch):
    monkeypatch.setattr("jobagent.job_input.MAX_TXT_BYTES", 16)
    with pytest.raises(UploadTooLarge):
        read_job_file(io.BytesIO(b"a" * 17), "jd.txt")


def test_pdf_over_limit_never_reaches_pdf_parser(monkeypatch):
    monkeypatch.setattr("jobagent.job_input.MAX_PDF_BYTES", 16)
    parser = Mock()
    monkeypatch.setattr("jobagent.job_input.extract_pdf_text", parser)
    with pytest.raises(UploadTooLarge):
        read_job_file(io.BytesIO(b"%PDF" + b"0" * 32), "jd.pdf")
    parser.assert_not_called()


def test_pasted_text_over_character_limit_is_rejected():
    with pytest.raises(ValueError, match="超过"):
        manual_job("岗位要求" * (MAX_JOB_TEXT_CHARS // 4 + 1), "")


def test_pasted_text_at_character_limit_is_accepted():
    candidate = manual_job("岗位要求" * (MAX_JOB_TEXT_CHARS // 4), "")
    assert len(candidate.raw_text) == MAX_JOB_TEXT_CHARS


def test_resume_upload_over_limit_returns_413_and_skips_llm(monkeypatch):
    from fastapi.testclient import TestClient

    from jobagent.api import app
    from jobagent.resume import OpenAIResumeProvider, get_resume_provider

    client_mock = Mock()
    provider = OpenAIResumeProvider(client=client_mock, model="test-model")
    monkeypatch.setattr("jobagent.api.MAX_PDF_BYTES", 1 * MB)
    app.dependency_overrides[get_resume_provider] = lambda: provider
    try:
        with TestClient(app) as client:
            response = client.post(
                "/resumes/parse",
                files={"file": ("resume.pdf", b"%PDF" + b"0" * (1 * MB + 1))},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 413
    assert "MB 上限" in response.json()["detail"]
    client_mock.chat.completions.create.assert_not_called()


def test_job_txt_upload_over_limit_returns_413():
    from fastapi.testclient import TestClient

    from jobagent.api import app

    with TestClient(app) as client:
        response = client.post(
            "/jobs/upload",
            files={"file": ("jd.txt", b"a" * (2 * MB + 1))},
        )
    assert response.status_code == 413
    assert "招聘 TXT" in response.json()["detail"]


def test_audio_over_limit_returns_413_before_wav_parsing(tmp_path, match_request, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from jobagent.api import app, database_session
    from jobagent.db import Base
    from jobagent.interview import get_interview_provider
    from jobagent.interview_schemas import InterviewPlan

    engine = create_engine(f"sqlite:///{tmp_path / 'limits.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def database():
        with factory() as session:
            yield session

    monkeypatch.setattr("jobagent.api.MAX_AUDIO_BYTES", 1 * MB)
    fake = Mock(model="test-model")
    fake.plan.return_value = InterviewPlan(
        topics=[
            {
                "title": f"主题{i}",
                "goal": "解释设计取舍",
                "expected_points": ["给出具体理由"],
                "questions": [f"基础问题{i}", f"进阶问题{i}", f"挑战问题{i}"],
            }
            for i in range(3)
        ]
    )
    app.dependency_overrides[database_session] = database
    app.dependency_overrides[get_interview_provider] = lambda: fake
    try:
        with TestClient(app) as client:
            created = client.post("/interviews", json=match_request.model_dump())
            assert created.status_code == 200
            response = client.post(
                f"/interviews/{created.json()['id']}/audio",
                files={"file": ("answer.wav", b"0" * (1 * MB + 1), "audio/wav")},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 413
    assert "录音文件" in response.json()["detail"]


def _annotation(**overrides):
    from jobagent.match_schemas import HumanAnnotation

    payload = {
        "annotator": "tester",
        "dimensions": [{"category": "skills", "score": 60}],
        "skill_gaps": ["RAG"],
        "notes": "",
    }
    payload.update(overrides)
    return HumanAnnotation.model_validate(payload)


def test_annotation_notes_over_limit_are_rejected():
    from jobagent.match_schemas import MAX_NOTES_CHARS

    with pytest.raises(ValueError):
        _annotation(notes="备" * (MAX_NOTES_CHARS + 1))


def test_annotation_too_many_skill_gaps_are_rejected():
    from jobagent.match_schemas import MAX_SKILL_GAPS

    with pytest.raises(ValueError):
        _annotation(skill_gaps=[f"技能{i}" for i in range(MAX_SKILL_GAPS + 1)])


def test_annotation_long_skill_gap_name_is_rejected():
    from jobagent.match_schemas import MAX_SKILL_GAP_CHARS

    with pytest.raises(ValueError):
        _annotation(skill_gaps=["x" * (MAX_SKILL_GAP_CHARS + 1)])


def test_annotation_within_limits_is_accepted():
    assert _annotation(notes="可以", skill_gaps=["RAG"]).notes == "可以"
