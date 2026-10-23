import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_collectors import search_html

from jobagent import collectors
from jobagent.api import app
from jobagent.collectors import collect_jobs, liepin_search_url, parse_liepin_list
from jobagent.job_catalog import CATALOG, CITIES, CITY_OPTIONS, ROLE_OPTIONS, ROLES
from jobagent.match_schemas import CollectionRequest


def test_official_catalog_has_unique_selectable_roles_and_city_codes():
    assert len(ROLE_OPTIONS) > 1000
    assert len(CITY_OPTIONS) > 300
    assert len(ROLES) == len(ROLE_OPTIONS)
    assert len(CITIES) == len(CITY_OPTIONS)
    assert len({c["zhilian_code"] for c in CITY_OPTIONS}) == len(CITY_OPTIONS)
    assert CITIES["hangzhou"] == ("杭州", "hz", "653")
    assert CITIES["city_635"] == ("南京", "nj", "635")
    assert ROLES["role_kuaiji"] == ("会计", "会计", "career/kuaiji")
    assert len({r["group"] for r in ROLE_OPTIONS}) == 99
    assert "https://www.zhaopin.com/citymap/" in CATALOG["sources"]


def test_options_endpoint_exposes_groups_and_searchable_pinyin():
    with TestClient(app) as client:
        options = client.get("/jobs/options").json()
    assert (
        next(r for r in options["roles"] if r["id"] == "role_kuaiji")["group"] == "财务/审计/税务"
    )
    city = next(c for c in options["cities"] if c["label"] == "南京")
    assert city["pinyin"] == "nanjing"
    assert city["hot"] is True


@pytest.mark.parametrize("field,value", [("role", "随意输入的岗位"), ("city", "任意城市")])
def test_collection_requires_a_real_catalog_selection(field, value):
    data = {"role": "python", "city": "hangzhou"}
    data[field] = value
    with pytest.raises(ValidationError, match="请选择"):
        CollectionRequest(**data)


def test_new_role_and_city_are_sent_to_actual_collection_query(monkeypatch):
    real_client = httpx.Client
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["jl"] == "635"
        assert request.url.params["kw"] == "会计"
        return httpx.Response(200, text=search_html(city="南京"))

    monkeypatch.setattr(
        collectors.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    request = CollectionRequest(role="role_kuaiji", city="city_635", source="zhilian", limit=20)
    result = collect_jobs(request)
    assert result.jobs[0].city == "南京"
    assert len(calls) == 2
    assert liepin_search_url(request) == "https://www.liepin.com/city-nj/career/kuaiji/"
    assert liepin_search_url(CollectionRequest(role="python", city="hangzhou")).endswith(
        "/city-hz/zppython/"
    )


def test_career_page_uses_its_public_job_links_and_pagination():
    html = (
        '<a href="https://www.liepin.com/job/123.shtml">会计</a>'
        '<a href="/city-nj/career/kuaiji/pn1/">下一页</a>'
    )
    links, next_page = parse_liepin_list(html)
    assert links == ["https://www.liepin.com/job/123.shtml"]
    assert next_page == "https://www.liepin.com/city-nj/career/kuaiji/pn1/"
