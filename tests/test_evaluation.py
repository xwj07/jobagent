import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobagent.api import app, database_session
from jobagent.db import Base
from jobagent.evaluation import compute_metrics, evaluation_summary, save_case, spearman
from jobagent.match_schemas import HumanAnnotation, MatchAnalysis
from jobagent.matching import build_report, get_match_provider
from jobagent.models import MatchCase


def test_micro_gap_metrics_count_per_pair_and_normalize_aliases():
    metrics = compute_metrics(
        [
            {
                "predicted_gaps": ["Python", "K8s"],
                "human_gaps": ["Kubernetes", "Redis"],
                "predicted_score": 50,
                "human_score": 60,
            },
            {
                "predicted_gaps": [],
                "human_gaps": ["Python"],
                "predicted_score": 70,
                "human_score": 80,
            },
        ]
    )
    assert (metrics["tp"], metrics["fp"], metrics["fn"]) == (1, 1, 2)
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == pytest.approx(1 / 3, abs=1e-6)
    assert metrics["f1"] == 0.4
    assert metrics["spearman"] == 1


def test_gap_in_different_pair_cannot_become_true_positive():
    metrics = compute_metrics(
        [
            {
                "predicted_gaps": ["Python"],
                "human_gaps": [],
                "predicted_score": 1,
                "human_score": 1,
            },
            {
                "predicted_gaps": [],
                "human_gaps": ["Python"],
                "predicted_score": 2,
                "human_score": 2,
            },
        ]
    )
    assert metrics["tp"] == 0
    assert metrics["fp"] == metrics["fn"] == 1


def test_spearman_averages_tied_ranks_against_published_example():
    assert spearman([1, 2, 3, 4, 5], [5, 6, 7, 8, 7]) == 0.820783
    assert spearman([1, 2, 3], [3, 2, 1]) == -1


def test_metrics_do_not_invent_scores_when_undefined():
    empty = compute_metrics([])
    assert empty["precision"] is None
    assert empty["recall"] is None
    assert empty["spearman"] is None
    assert spearman([1, 1], [2, 3]) is None


@pytest.fixture()
def eval_client(tmp_path, match_request, match_analysis):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'evaluation.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    report = build_report(match_request, match_analysis, "test-model")

    def session_dependency():
        with factory() as session:
            yield session

    class FixedProvider:
        def match(self, _request):
            return report

    app.dependency_overrides[database_session] = session_dependency
    app.dependency_overrides[get_match_provider] = FixedProvider
    with TestClient(app) as client:
        yield client, factory, report
    app.dependency_overrides.clear()
    engine.dispose()


def test_annotation_flow_is_blind_and_only_labelled_pairs_are_evaluated(eval_client, match_request):
    client, factory, report = eval_client
    assert client.get("/evaluation/summary").json()["labelled_pairs"] == 0
    response = client.post("/matches", json=match_request.model_dump())
    assert response.status_code == 200
    assert response.json()["total_score"] == 58.33
    assert client.get("/evaluation/summary").json()["groups"] == []
    case = client.get(f"/evaluation/cases/{report.case_id}").json()
    assert "prediction" not in case
    assert "total_score" not in case
    assert case["annotation"] is None
    annotation = {
        "annotator": "Human A",
        "dimensions": [
            {"category": "skills", "score": 50},
            {"category": "education", "score": 100},
        ],
        "skill_gaps": ["Kubernetes"],
        "notes": "独立核对原始材料",
    }
    saved = client.put(f"/evaluation/cases/{report.case_id}/annotation", json=annotation)
    assert saved.status_code == 200
    assert saved.json()["human_score"] == 58.33
    summary = client.get("/evaluation/summary").json()
    assert summary["labelled_pairs"] == 1
    assert summary["target_reached"] is False
    assert summary["groups"][0]["precision"] == summary["groups"][0]["recall"] == 1
    assert summary["groups"][0]["spearman"] is None
    assert client.get("/evaluation/export").text.count('"pair_id"') == 1
    # Rerunning a pair does not duplicate it or overwrite its independent human annotation.
    client.post("/matches", json=match_request.model_dump())
    with factory() as session:
        assert session.query(MatchCase).count() == 1
        assert session.get(MatchCase, report.case_id).annotation["annotator"] == "Human A"


def test_missing_pair_is_not_annotated(eval_client):
    client, _, _ = eval_client
    response = client.get("/evaluation/cases/not-found")
    assert response.status_code == 404


def test_unlabelled_examples_never_enter_metrics(eval_client, match_request, match_analysis):
    _, factory, _ = eval_client
    report = build_report(match_request, match_analysis, "test-model")
    with factory() as session:
        save_case(session, match_request, report)
        assert evaluation_summary(session)["groups"] == []


def test_repeated_human_dimensions_are_rejected():
    with pytest.raises(ValueError, match="重复"):
        HumanAnnotation.model_validate(
            {
                "annotator": "A",
                "skill_gaps": [],
                "dimensions": [
                    {"category": "skills", "score": 50},
                    {"category": "skills", "score": 80},
                ],
            }
        )


def test_match_validation_error_does_not_expose_model_payload(eval_client, match_request):
    client, _, _ = eval_client

    class InvalidProvider:
        def match(self, _request):
            return MatchAnalysis.model_validate({"summary": "private model payload"})

    app.dependency_overrides[get_match_provider] = InvalidProvider
    response = client.post("/matches", json=match_request.model_dump())
    assert response.status_code == 502
    assert "private model payload" not in response.text
    assert "input_value" not in response.text
    assert "pydantic.dev" not in response.text
