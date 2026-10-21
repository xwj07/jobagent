import pytest

from jobagent.match_schemas import MatchAnalysis, MatchRequest


@pytest.fixture()
def match_request():
    return MatchRequest.model_validate(
        {
            "resume": {
                "name": "Alice",
                "target_role": "Python开发",
                "education": [
                    {
                        "school": "大学",
                        "degree": "本科",
                        "major": "计算机",
                        "start_date": "2019",
                        "end_date": "2023",
                    }
                ],
                "work_experience": [],
                "projects": [],
                "skills": [{"name": "Python", "evidence": "使用 Python 编写接口"}],
            },
            "job": {
                "title": "Python工程师",
                "company": "Example",
                "city": "杭州",
                "salary": "20-30K",
                "source": "zhilian",
                "url": "https://www.zhaopin.com/jobdetail/example.htm",
                "raw_text": "要求 Python 和 Kubernetes。本科及以上。Redis 优先。",
            },
        }
    )


@pytest.fixture()
def match_analysis():
    return MatchAnalysis.model_validate(
        {
            "summary": "Python 已体现，Kubernetes 未体现。",
            "requirements": [
                {
                    "requirement": "Python",
                    "category": "skills",
                    "skill_name": "Python",
                    "required": True,
                    "status": "met",
                    "jd_evidence": "Python",
                    "resume_evidence": ["使用 Python 编写接口"],
                    "explanation": "有直接证据",
                    "suggestion": None,
                },
                {
                    "requirement": "Kubernetes",
                    "category": "skills",
                    "skill_name": "K8s",
                    "required": True,
                    "status": "missing",
                    "jd_evidence": "Kubernetes",
                    "resume_evidence": [],
                    "explanation": "简历未体现",
                    "suggestion": "完成本地容器部署练习并记录操作过程",
                },
                {
                    "requirement": "本科",
                    "category": "education",
                    "skill_name": None,
                    "required": True,
                    "status": "met",
                    "jd_evidence": "本科及以上",
                    "resume_evidence": ["本科"],
                    "explanation": "学历符合",
                    "suggestion": None,
                },
            ],
        }
    )
