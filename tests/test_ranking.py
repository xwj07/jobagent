from fastapi.testclient import TestClient

from jobagent.api import app
from jobagent.match_schemas import RankRequest
from jobagent.ranking import rank_jobs


def test_ranks_by_jd_skill_coverage_with_aliases(match_request):
    request = RankRequest(
        resume=match_request.resume,
        jobs=[
            match_request.job.model_copy(
                update={"title": "B", "raw_text": "使用 Python 和 k8s 部署接口"}
            ),
            match_request.job.model_copy(update={"title": "A", "raw_text": "要求 Python 开发服务"}),
            match_request.job.model_copy(
                update={"title": "C", "raw_text": "要求 JavaScript 和 Redis"}
            ),
        ],
    )
    ranked = rank_jobs(request)
    assert [r.job.title for r in ranked] == ["A", "B", "C"]
    assert [r.score for r in ranked] == [100, 50, 0]
    assert ranked[1].missing_skills == ["kubernetes"]


def test_project_technologies_count_and_company_metadata_does_not(match_request):
    request = RankRequest(
        resume=match_request.resume,
        jobs=[
            match_request.job.model_copy(
                update={
                    "company": "Java公司",
                    "raw_text": "Java公司，Python开发。",
                    "description": "要求 Python 编写接口。",
                }
            )
        ],
    )
    ranked = rank_jobs(request)
    assert ranked[0].matched_skills == ["python"]
    assert ranked[0].missing_skills == []


def test_no_skill_keywords_is_not_presented_as_zero_percent_fit(match_request):
    request = RankRequest(
        resume=match_request.resume,
        jobs=[
            match_request.job.model_copy(
                update={
                    "raw_text": "负责团队日常协作，认真完成工作任务。",
                }
            )
        ],
    )
    assert rank_jobs(request)[0].score is None


def test_rank_endpoint_returns_explainable_skills_without_model_call(match_request):
    with TestClient(app) as client:
        response = client.post(
            "/jobs/rank",
            json={
                "resume": match_request.resume.model_dump(),
                "jobs": [match_request.job.model_dump()],
            },
        )
    assert response.status_code == 200
    assert response.json()[0]["matched_skills"] == ["python"]
    assert "kubernetes" in response.json()[0]["missing_skills"]
