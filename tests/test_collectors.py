import json

import httpx
import pytest

from jobagent import collectors
from jobagent.collectors import (
    CollectionError,
    collect_jobs,
    deduplicate,
    initial_state,
    parse_liepin_detail,
    parse_liepin_list,
    parse_zhilian,
)
from jobagent.match_schemas import CollectionRequest


def search_html(number="EXAMPLE", city="杭州"):
    state = {
        "positionList": [
            {
                "companyName": "Example",
                "workCity": city,
                "publishTime": "2026-10-21",
                "jobDetailData": {
                    "position": {
                        "base": {
                            "positionName": "Python工程师",
                            "salary": "20-30K",
                            "positionNumber": number,
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


def list_html(ids, next_page=False):
    cards = "".join(
        f'<a class="job-card" href="https://m.liepin.com/job/{i}.shtml">卡片</a>' for i in ids
    )
    if next_page:
        cards += '<a href="https://m.liepin.com/city-hz/zppython/pn1/">下一页</a>'
    return cards


def detail_html(number=1, city="杭州"):
    data = {
        "@type": "JobPosting",
        "title": f"Python工程师{number}",
        "description": f"负责接口开发，要求 Python 和 PostgreSQL。岗位编号{number}",
        "hiringOrganization": {"name": "真实公司"},
        "jobLocation": {"address": {"addressRegion": city}},
        "experienceRequirements": "3-5年",
        "educationRequirements": "本科",
        "datePosted": "2026-10-20T18:03:16+08:00",
        "url": f"https://www.liepin.com/job/{number}.shtml",
    }
    return (
        '<span class="salary">20-30k·14薪</span><script type="application/ld+json">'
        + json.dumps(data)
        + "</script>"
    )


def mock_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(
        collectors.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )


def test_zhilian_reads_full_jd_and_preserves_metadata():
    job = parse_zhilian(search_html())[0]
    assert job.company == "Example"
    assert "熟悉 Python\n有 Kubernetes 经验" in job.raw_text
    assert job.url == "https://www.zhaopin.com/jobdetail/EXAMPLE.htm"
    assert job.city == "杭州"
    assert (job.education, job.experience, job.published_at) == ("本科", "3-5年", "2026-10-21")


def test_empty_card_is_not_full_jd():
    state = initial_state(search_html())
    state["positionList"][0]["jobDetailData"]["position"]["desc"]["description"] = ""
    with pytest.raises(CollectionError, match="完整 JD"):
        parse_zhilian(f"<script>__INITIAL_STATE__={json.dumps(state)}</script>")
    with pytest.raises(CollectionError, match="完整岗位"):
        parse_liepin_detail("<div>岗位卡片摘要</div>")


def test_missing_state_is_reported():
    with pytest.raises(CollectionError, match="登录"):
        initial_state("<html>Login required</html>")


def test_liepin_keeps_original_salary_education_and_full_description():
    links, next_page = parse_liepin_list(list_html([1, 1, 2], True))
    assert len(links) == 2
    assert next_page.endswith("/pn1/")
    job = parse_liepin_detail(detail_html())
    assert job.salary == "20-30k·14薪"
    assert job.education == "本科"
    assert job.experience == "3-5年"
    assert job.city == "杭州"
    assert job.source == "liepin"
    assert job.description == "负责接口开发，要求 Python 和 PostgreSQL。岗位编号1"


def test_liepin_paginates_and_reads_fifty_full_details(monkeypatch):
    details = []

    def handler(request):
        if "/city-" in request.url.path:
            return httpx.Response(
                200,
                text=list_html(range(40, 80))
                if "/pn1/" in request.url.path
                else list_html(range(40), True),
            )
        number = int(request.url.path.rsplit("/", 1)[-1].split(".")[0])
        details.append(number)
        return httpx.Response(200, text=detail_html(number))

    mock_client(monkeypatch, handler)
    result = collect_jobs(
        CollectionRequest(role="python", city="hangzhou", source="liepin", limit=50)
    )
    assert len(details) == len(result.jobs) == 50
    assert result.sources[0].count == 50
    assert len({job.url for job in result.jobs}) == 50


def test_repeated_zhilian_page_stops_and_is_not_counted_twice(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text=search_html())

    mock_client(monkeypatch, handler)
    result = collect_jobs(
        CollectionRequest(role="python", city="hangzhou", source="zhilian", limit=100)
    )
    assert len(calls) == 2
    assert len(result.jobs) == 1
    assert "重复" in result.sources[0].message


def test_block_stops_after_current_batch_and_other_source_still_works(monkeypatch):
    details = []

    def handler(request):
        if request.url.host == "www.zhaopin.com":
            return httpx.Response(200, text=search_html())
        if "/city-" in request.url.path:
            return httpx.Response(200, text=list_html(range(40), True))
        details.append(request.url)
        return httpx.Response(403)

    mock_client(monkeypatch, handler)
    result = collect_jobs(
        CollectionRequest(role="python", city="hangzhou", source="both", limit=50)
    )
    assert len(details) == 4
    assert result.sources[0].status == "blocked"
    assert result.sources[1].status == "success"
    assert [job.source for job in result.jobs] == ["zhilian"]


def test_job_from_other_city_is_not_labelled_as_selected_city(monkeypatch):
    mock_client(monkeypatch, lambda request: httpx.Response(200, text=search_html(city="上海")))
    result = collect_jobs(CollectionRequest(role="python", city="hangzhou", source="zhilian"))
    assert result.jobs == []


def test_deduplicate_preserves_distinct_postings():
    first = parse_liepin_detail(detail_html(1))
    second = parse_liepin_detail(detail_html(2))
    assert deduplicate([first, first.model_copy(), second]) == [first, second]
