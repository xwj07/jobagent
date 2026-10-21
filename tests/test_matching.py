import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jobagent.match_schemas import ReferencedAnalysis
from jobagent.matching import (
    MatchProvider,
    build_report,
    case_id,
    evidence_catalog,
    resolve_evidence,
)


def reference_analysis(request, analysis):
    catalog = evidence_catalog(request)
    items = []
    for item in analysis.requirements:
        items.append(
            {
                **item.model_dump(exclude={"jd_evidence", "resume_evidence"}),
                "jd_evidence_id": next(
                    p["id"] for p in catalog["job"] if item.jd_evidence in p["text"]
                ),
                "resume_evidence_ids": [
                    next(p["id"] for p in catalog["resume"] if quote in p["text"])
                    for quote in item.resume_evidence
                ],
            }
        )
    return ReferencedAnalysis(summary=analysis.summary, requirements=items)


def test_scores_use_fixed_rubric_and_exclude_unmentioned_dimensions(match_request, match_analysis):
    report = build_report(match_request, match_analysis, "test-model")
    assert report.total_score == 58.33
    assert {item.category for item in report.dimensions} == {"skills", "education"}
    assert report.skill_gaps == ["kubernetes"]
    assert sum(item.weight for item in report.dimensions) == pytest.approx(100)


def test_optional_requirements_have_half_weight(match_request, match_analysis):
    match_analysis.requirements = match_analysis.requirements[:2]
    match_analysis.requirements[1].required = False
    report = build_report(match_request, match_analysis, "test-model")
    assert report.total_score == 66.67


def test_partial_skill_is_gap_and_receives_half_credit(match_request, match_analysis):
    match_analysis.requirements = match_analysis.requirements[:1]
    requirement = match_analysis.requirements[0]
    requirement.status = "partial"
    requirement.suggestion = "补充具体项目使用证据"
    report = build_report(match_request, match_analysis, "test-model")
    assert report.total_score == 50
    assert report.skill_gaps == ["python"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("jd_evidence", "JD 没有这句话"),
        ("resume_evidence", ["拥有十年 Kubernetes 经验"]),
    ],
)
def test_fabricated_evidence_is_not_accepted(match_request, match_analysis, field, value):
    setattr(match_analysis.requirements[0], field, value)
    with pytest.raises(ValueError, match="原文"):
        build_report(match_request, match_analysis, "test-model")


def test_same_input_pair_has_stable_id(match_request):
    assert case_id(match_request) == case_id(match_request.model_copy(deep=True))
    changed = match_request.model_copy(deep=True)
    changed.job.raw_text += " 新增要求"
    assert case_id(changed) != case_id(match_request)


def test_model_sees_only_resume_and_job_not_human_labels(match_request, match_analysis):
    client = Mock()
    references = reference_analysis(match_request, match_analysis)
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=references.model_dump_json()))]
    )
    report = MatchProvider(client, "test-model").match(match_request)
    request = client.chat.completions.create.call_args.kwargs
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    data = json.loads(request["messages"][1]["content"])
    assert set(data) == {"resume", "job", "evidence"}
    assert report.total_score == 58.33
    assert report.requirements[0].jd_evidence in match_request.job.raw_text


def test_model_selects_source_ids_and_program_copies_original_text(match_request, match_analysis):
    catalog = evidence_catalog(match_request)
    references = reference_analysis(match_request, match_analysis)
    analysis = resolve_evidence(references, catalog)
    python = analysis.requirements[0]
    assert python.resume_evidence == ["使用 Python 编写接口"]
    assert python.jd_evidence == "要求 Python 和 Kubernetes。"
    assert (
        "jd_evidence"
        not in ReferencedAnalysis.model_json_schema()["$defs"]["ReferencedRequirement"][
            "properties"
        ]
    )
    assert all(p["path"] not in {"name", "target_role"} for p in catalog["resume"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("jd_evidence_id", 999),
        ("resume_evidence_ids", [999]),
        ("resume_evidence_ids", [-1]),
    ],
)
def test_invalid_evidence_reference_is_rejected(match_request, match_analysis, field, value):
    references = reference_analysis(match_request, match_analysis)
    setattr(references.requirements[0], field, value)
    with pytest.raises(ValueError, match="编号不存在"):
        resolve_evidence(references, evidence_catalog(match_request))


def test_jd_communication_requirement_cannot_supply_resume_evidence(match_request):
    match_request.job.raw_text = "具备良好的业务理解能力与跨团队沟通能力。"
    references = ReferencedAnalysis.model_validate(
        {
            "summary": "简历中未体现相关能力。",
            "requirements": [
                {
                    "requirement": "业务理解与跨团队沟通",
                    "category": "experience",
                    "skill_name": None,
                    "required": True,
                    "status": "missing",
                    "jd_evidence_id": 0,
                    "resume_evidence_ids": [],
                    "explanation": "简历未提供相关协作经历。",
                    "suggestion": "补充真实项目中与业务或团队协作的具体实例。",
                }
            ],
        }
    )
    analysis = resolve_evidence(references, evidence_catalog(match_request))
    report = build_report(match_request, analysis, "test-model")
    assert report.total_score == 0
    assert report.requirements[0].resume_evidence == []
    assert report.requirements[0].jd_evidence == match_request.job.raw_text
