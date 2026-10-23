import json
from collections import Counter
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from jobagent import collectors
from jobagent.collectors import (
    CollectionError,
    collect_jobs,
    parse_nowcoder_job,
    source_search_urls,
)
from jobagent.match_schemas import CollectionRequest


def item(number=1, kind=2, city="杭州/上海"):
    tags = [city, "本科", "1-3年"]
    return {"data": {
        "id": number, "jobName": f"Python 工程师 {number}", "recruitType": kind,
        "ext": json.dumps({"infos": "<p>开发 Python 服务，使用 FastAPI。</p>",
                           "requirements": "熟悉 SQL 和 Docker。"}),
        "pcTagInfo": {"jobInfoTagList": [{"tag": {"title": tag}} for tag in tags]},
        "salaryType": 1 if kind == 2 else 2, "salaryMin": 200 if kind == 2 else 15,
        "salaryMax": 300 if kind == 2 else 25, "salaryMonth": 14,
        "recommendInternCompany": {"companyName": "Example Company"},
        "refreshTime": 1792700000000,
    }}


def mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(collectors.httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handler),
    ))


def test_nowcoder_preserves_full_jd_multiple_cities_and_daily_pay():
    job = parse_nowcoder_job(item())
    assert job.city == "杭州/上海"
    assert job.salary == "200-300元/天"
    assert job.recruitment_type == "实习"
    assert job.education == "本科"
    assert "FastAPI" in job.description and "SQL" in job.description
    assert job.url == "https://www.nowcoder.com/jobs/detail/1"
    assert job.source == "nowcoder"
    assert parse_nowcoder_job(item(kind=3)).salary == "15-25K/月 · 14薪"


def test_nowcoder_does_not_count_card_without_full_jd():
    value = item()
    value["data"]["ext"] = "{}"
    with pytest.raises(CollectionError, match="完整"):
        parse_nowcoder_job(value)


def test_all_categories_are_interleaved_before_limiting(monkeypatch):
    calls = []

    def handler(request):
        body = parse_qs(request.content.decode())
        kind = int(body["recruitType"][0])
        calls.append(kind)
        assert request.url.path == "/np-api/u/job/square-search"
        assert json.loads(body["jobCity"][0]) == ["杭州"]
        assert "Python" in body["query"][0]
        return httpx.Response(200, json={"code": 0, "data": {
            "datas": [item(kind * 100 + i, kind) for i in range(20)], "totalPage": 5,
        }})

    mock_client(monkeypatch, handler)
    result = collect_jobs(CollectionRequest(role="python", city="hangzhou", source="nowcoder"))
    assert calls == [1, 2, 3]
    assert len(result.jobs) == 50
    assert Counter(j.recruitment_type for j in result.jobs) == {"校招": 17, "实习": 17, "社招": 16}
    assert len(result.sources[0].search_urls) == 3


def test_single_category_stops_repeated_pages_without_relabelling_city(monkeypatch):
    calls = []

    def handler(request):
        body = parse_qs(request.content.decode())
        calls.append(int(body["page"][0]))
        assert body["recruitType"] == ["3"]
        return httpx.Response(200, json={"code": 0, "data": {
            "datas": [item(1, 3), item(2, 3, "北京")], "totalPage": 5,
        }})

    mock_client(monkeypatch, handler)
    result = collect_jobs(CollectionRequest(
        role="python", city="hangzhou", source="nowcoder", recruitment_type="social",
    ))
    assert calls == [1, 2]
    assert len(result.jobs) == 1
    assert result.jobs[0].city == "杭州/上海"
    assert result.jobs[0].recruitment_type == "社招"


def test_login_requirement_stops_and_returns_original_site_links(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"code": 999, "msg": "请登录"})

    mock_client(monkeypatch, handler)
    result = collect_jobs(CollectionRequest(role="python", city="hangzhou", source="nowcoder"))
    assert len(calls) == 1
    assert result.sources[0].status == "blocked"
    assert set(result.sources[0].search_urls) == {"牛客校招", "牛客实习", "牛客社招"}


def test_liepin_failure_has_link_to_selected_role_and_city(monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(403))
    request = CollectionRequest(role="python", city="hangzhou", source="liepin")
    result = collect_jobs(request)
    url = result.sources[0].search_urls["猎聘"]
    assert url == collectors.liepin_search_url(request)
    nowcoder = source_search_urls(request, "nowcoder")
    for url in nowcoder.values():
        query = parse_qs(urlparse(url).query)
        assert query["city"] == ["杭州"]
        assert "Python" in query["search"][0]
