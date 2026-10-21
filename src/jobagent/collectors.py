"""Read public job pages; report login/security blocks as collection results."""

import json

import httpx
from bs4 import BeautifulSoup

from .match_schemas import CollectionRequest, CollectionResult, JobCandidate, SourceResult

ROLES = {
    "python": ("Python 开发", "Python开发"),
    "ai_application": ("AI 应用工程师", "AI应用工程师"),
    "java": ("Java 开发", "Java开发"),
    "frontend": ("前端开发", "前端开发"),
    "data": ("数据开发", "数据开发"),
    "ml": ("机器学习工程师", "机器学习"),
}
CITIES = {
    "hangzhou": ("杭州", "101210100", "653"),
    "beijing": ("北京", "101010100", "530"),
    "shanghai": ("上海", "101020100", "538"),
    "shenzhen": ("深圳", "101280600", "765"),
    "guangzhou": ("广州", "101280100", "763"),
    "chengdu": ("成都", "101270100", "801"),
}
SOURCE_LABELS = {"boss": "BOSS 直聘", "zhilian": "智联招聘"}


class CollectionError(ValueError):
    pass


class CollectionBlocked(CollectionError):
    pass


def initial_state(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        text = script.string or ""
        if "__INITIAL_STATE__=" in text:
            return json.JSONDecoder().raw_decode(text.split("__INITIAL_STATE__=", 1)[1])[0]
    raise CollectionError("页面未返回职位数据，可能需要登录或页面结构已变化。")


def parse_zhilian(html: str, limit: int = 5) -> list[JobCandidate]:
    state = initial_state(html)
    if "positionList" not in state:
        raise CollectionError("智联搜索页未提供职位列表，无法完成采集。")
    jobs = []
    for item in state["positionList"][:limit]:
        position = item["jobDetailData"]["position"]
        base = position["base"]
        description = position["desc"]["description"]
        description = BeautifulSoup(description, "html.parser").get_text("\n", strip=True)
        if not description:
            raise CollectionError("智联返回了岗位卡片，但未提供完整 JD。")
        title = base["positionName"]
        salary = base["salary"]
        company = item["companyName"]
        city = item["workCity"]
        job_url = f"https://www.zhaopin.com/jobdetail/{base['positionNumber']}.htm"
        text = "\n".join(
            [
                title,
                company,
                city,
                salary,
                base["positionWorkingExp"],
                base["education"],
                description,
            ]
        )
        jobs.append(
            JobCandidate(
                title=title,
                company=company,
                city=city,
                salary=salary,
                source="zhilian",
                url=job_url,
                raw_text=text,
            )
        )
    return jobs


def parse_boss_detail(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select(".job-sec-text")
    if not blocks:
        raise CollectionError("BOSS 职位详情未提供完整 JD，可能需要登录或安全验证。")
    return "\n".join(block.get_text("\n", strip=True) for block in blocks)


def collect_boss(client: httpx.Client, keyword: str, city: tuple) -> list[JobCandidate]:
    response = client.get(
        "https://www.zhipin.com/wapi/zpgeek/search/joblist.json",
        params={"scene": 1, "query": keyword, "city": city[1], "page": 1, "pageSize": 5},
    )
    response.raise_for_status()
    data = response.json()
    if data["code"] != 0:
        raise CollectionBlocked(
            f"BOSS 返回 code {data['code']}：{data['message']}。本次请求被平台阻断，未获取岗位。"
        )
    jobs = []
    for item in data["zpData"]["jobList"][:5]:
        url = f"https://www.zhipin.com/job_detail/{item['encryptJobId']}.html"
        detail = client.get(url)
        detail.raise_for_status()
        if "/security" in str(detail.url) or "/passport" in str(detail.url):
            raise CollectionBlocked("BOSS 职位详情跳转至安全验证，当前无法取得完整 JD。")
        description = parse_boss_detail(detail.text)
        title, company, salary = item["jobName"], item["brandName"], item["salaryDesc"]
        actual_city = item["cityName"]
        jobs.append(
            JobCandidate(
                title=title,
                company=company,
                city=actual_city,
                salary=salary,
                source="boss",
                url=url,
                raw_text="\n".join([title, company, actual_city, salary, description]),
            )
        )
    return jobs


def collect_jobs(request: CollectionRequest) -> CollectionResult:
    keyword = ROLES[request.role][1]
    city = CITIES[request.city]
    sources = ["boss", "zhilian"] if request.source == "both" else [request.source]
    jobs, results = [], []
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        for source in sources:
            try:
                if source == "boss":
                    items = collect_boss(client, keyword, city)
                else:
                    response = client.get(
                        "https://www.zhaopin.com/jobs/", params={"jl": city[2], "kw": keyword}
                    )
                    response.raise_for_status()
                    items = parse_zhilian(response.text)
                jobs.extend(items)
                results.append(
                    SourceResult(
                        source=source,
                        status="success",
                        count=len(items),
                        message=f"已获取 {len(items)} 个岗位的完整 JD。",
                    )
                )
            except CollectionBlocked as exc:
                results.append(
                    SourceResult(source=source, status="blocked", count=0, message=str(exc))
                )
            except (httpx.HTTPError, CollectionError, KeyError, json.JSONDecodeError) as exc:
                results.append(
                    SourceResult(
                        source=source,
                        status="error",
                        count=0,
                        message=f"{SOURCE_LABELS[source]}采集失败：{exc}",
                    )
                )
    return CollectionResult(jobs=jobs, sources=results)
