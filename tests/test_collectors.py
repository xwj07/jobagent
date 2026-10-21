import json

import httpx
import pytest

from jobagent import collectors
from jobagent.collectors import CollectionError, collect_jobs, initial_state, parse_zhilian
from jobagent.match_schemas import CollectionRequest


def search_html():
    state = {
        "positionList": [
            {
                "companyName": "Example",
                "workCity": "杭州",
                "jobDetailData": {
                    "position": {
                        "base": {
                            "positionName": "Python工程师",
                            "salary": "20-30K",
                            "positionNumber": "EXAMPLE",
                            "positionWorkingExp": "3-5年",
                            "education": "本科",
                        },
                        "desc": {"description": "<p>熟悉 Python</p><p>有 Kubernetes 经验</p>"},
                    }
                },
            }
        ]
    }
    return f"<script>__INITIAL_STATE__={json.dumps(state)};window.after=true;</script>"


def test_zhilian_reads_full_jd_and_preserves_metadata():
    jobs = parse_zhilian(search_html())
    assert len(jobs) == 1
    assert jobs[0].company == "Example"
    assert "熟悉 Python\n有 Kubernetes 经验" in jobs[0].raw_text
    assert jobs[0].url == "https://www.zhaopin.com/jobdetail/EXAMPLE.htm"
    assert jobs[0].city == "杭州"


def test_zhilian_does_not_treat_empty_card_as_full_jd():
    html = search_html().replace("<p>熟悉 Python</p><p>有 Kubernetes 经验</p>", "")
    # The script is JSON-escaped, so modify the actual decoded state.
    state = initial_state(html)
    state["positionList"][0]["jobDetailData"]["position"]["desc"]["description"] = ""
    with pytest.raises(CollectionError, match="完整 JD"):
        parse_zhilian(f"<script>__INITIAL_STATE__={json.dumps(state)}</script>")


def test_missing_state_is_reported():
    with pytest.raises(CollectionError, match="登录"):
        initial_state("<html>Login required</html>")


def test_boss_block_is_visible_and_zhilian_is_collected(monkeypatch):
    real_client = httpx.Client
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.host == "www.zhipin.com":
            return httpx.Response(200, json={"code": 37, "message": "您的环境存在异常"})
        assert request.url.params["jl"] == "653"
        assert request.url.params["kw"] == "Python开发"
        return httpx.Response(200, text=search_html())

    monkeypatch.setattr(
        collectors.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    result = collect_jobs(CollectionRequest(role="python", city="hangzhou", source="both"))
    assert len(requests) == 2
    assert result.sources[0].status == "blocked"
    assert "code 37" in result.sources[0].message
    assert result.sources[1].status == "success"
    assert len(result.jobs) == 1
    assert all(job.source == "zhilian" for job in result.jobs)


def test_boss_success_fetches_detail_before_returning_job(monkeypatch):
    real_client = httpx.Client

    def handle(request):
        if "joblist" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "zpData": {
                        "jobList": [
                            {
                                "encryptJobId": "example",
                                "jobName": "Python工程师",
                                "brandName": "Example",
                                "salaryDesc": "20-30K",
                                "cityName": "杭州",
                            }
                        ]
                    },
                },
            )
        return httpx.Response(200, text='<div class="job-sec-text">要求 Python 和 Kubernetes</div>')

    monkeypatch.setattr(
        collectors.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handle)),
    )
    result = collect_jobs(CollectionRequest(role="python", city="hangzhou", source="boss"))
    assert result.sources[0].status == "success"
    assert "要求 Python 和 Kubernetes" in result.jobs[0].raw_text
