"""Collect full public JDs from Liepin and Zhilian, preserving source metadata."""

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from urllib.parse import urlencode, urljoin

import httpx
from bs4 import BeautifulSoup

from .job_catalog import CITIES, ROLES
from .match_schemas import CollectionRequest, CollectionResult, JobCandidate, SourceResult

SOURCE_LABELS = {"liepin": "猎聘", "zhilian": "智联招聘", "nowcoder": "牛客"}
NOWCODER_TYPES = {
    "campus": (1, "校招", "school/jobs"),
    "intern": (2, "实习", "intern/center"),
    "social": (3, "社招", "fulltime/center"),
}


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


def parse_zhilian(html: str, limit: int = 100) -> list[JobCandidate]:
    state = initial_state(html)
    if "positionList" not in state:
        raise CollectionError("智联搜索页未提供职位列表，无法完成采集。")
    jobs = []
    for item in state["positionList"][:limit]:
        position = item["jobDetailData"]["position"]
        base = position["base"]
        description = BeautifulSoup(position["desc"]["description"], "html.parser").get_text(
            "\n", strip=True
        )
        if not description:
            raise CollectionError("智联返回了岗位卡片，但未提供完整 JD。")
        title, salary = base["positionName"], base["salary"]
        company, city = item["companyName"], item["workCity"]
        jobs.append(
            JobCandidate(
                title=title,
                company=company,
                city=city,
                salary=salary,
                source="zhilian",
                url=f"https://www.zhaopin.com/jobdetail/{base['positionNumber']}.htm",
                education=base["education"],
                experience=base["positionWorkingExp"],
                published_at=item.get("publishTime", ""),
                description=description,
                raw_text="\n".join(
                    [
                        title,
                        company,
                        city,
                        salary,
                        base["positionWorkingExp"],
                        base["education"],
                        description,
                    ]
                ),
            )
        )
    return jobs


def parse_liepin_list(html: str) -> tuple[list[str], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    links = list(
        dict.fromkeys(
            a["href"]
            for a in soup.select("a[href]")
            if re.fullmatch(r"https://(?:m|www)\.liepin\.com/(job|a)/\d+\.shtml", a["href"])
        )
    )
    if not links:
        raise CollectionError("猎聘页面未提供公开岗位列表。")
    next_link = next(
        (a["href"] for a in soup.select("a[href]") if a.get_text(strip=True) == "下一页"), None
    )
    if next_link:
        next_link = urljoin("https://www.liepin.com", next_link)
        if not re.match(r"https://(?:m|www)\.liepin\.com/city-", next_link):
            raise CollectionError("猎聘下一页链接不是公开城市职位页。")
    return links, next_link


def parse_liepin_detail(html: str) -> JobCandidate:
    soup = BeautifulSoup(html, "html.parser")
    data = next(
        (
            json.loads(script.string)
            for script in soup.select('script[type="application/ld+json"]')
            if script.string and '"JobPosting"' in script.string
        ),
        None,
    )
    if data is None:
        raise CollectionError("猎聘职位详情缺少完整岗位数据，未将卡片摘要计入结果。")
    description = BeautifulSoup(data["description"].replace("\\n", "\n"), "html.parser").get_text(
        "\n", strip=True
    )
    if not description:
        raise CollectionError("猎聘职位描述为空。")
    salary_element = soup.select_one(".salary")
    if salary_element is None:
        raise CollectionError("猎聘职位详情未返回原始薪资。")
    salary = salary_element.get_text(strip=True)
    company = data["hiringOrganization"]["name"]
    city = data["jobLocation"]["address"]["addressRegion"]
    experience, education = (
        data.get("experienceRequirements", ""),
        data.get("educationRequirements", ""),
    )
    return JobCandidate(
        title=data["title"],
        company=company,
        city=city,
        salary=salary,
        source="liepin",
        url=data["url"],
        education=education,
        experience=experience,
        published_at=data.get("datePosted", ""),
        description=description,
        raw_text="\n".join(
            [data["title"], company, city, salary, experience, education, description]
        ),
    )


def public_page(client: httpx.Client, url: str, **kwargs) -> str:
    response = client.get(url, **kwargs)
    if (
        response.status_code in (403, 429)
        or "猎聘安全中心" in response.text
        or any(
            part in str(response.url) for part in ("/captcha", "/security", "/passport", "/login")
        )
    ):
        raise CollectionBlocked("平台要求登录、安全验证或限制访问，已停止该来源的后续采集。")
    response.raise_for_status()
    return response.text


def deduplicate(jobs: list[JobCandidate]) -> list[JobCandidate]:
    seen_urls, seen_content, result = set(), set(), []
    for job in jobs:
        key = hashlib.sha256(
            re.sub(r"\s+", "", job.company + job.title + job.raw_text).encode()
        ).hexdigest()
        if (job.url and job.url in seen_urls) or key in seen_content:
            continue
        seen_urls.add(job.url)
        seen_content.add(key)
        result.append(job)
    return result


def liepin_search_url(request: CollectionRequest) -> str:
    city = CITIES[request.city]
    path = ROLES[request.role][2]
    host = "www" if path.startswith("career/") else "m"
    return f"https://{host}.liepin.com/city-{city[1]}/{path}/"


def source_search_urls(request: CollectionRequest, source: str) -> dict[str, str]:
    query = urlencode({"city": CITIES[request.city][0], "search": ROLES[request.role][1]})
    if source == "nowcoder":
        kinds = NOWCODER_TYPES if request.recruitment_type == "all" else [request.recruitment_type]
        return {
            f"牛客{NOWCODER_TYPES[kind][1]}":
            f"https://www.nowcoder.com/jobs/{NOWCODER_TYPES[kind][2]}?{query}"
            for kind in kinds
        }
    if source == "liepin":
        return {"猎聘": liepin_search_url(request)}
    return {"智联招聘": "https://www.zhaopin.com/jobs/?" + urlencode({
        "jl": CITIES[request.city][2], "kw": ROLES[request.role][1],
    })}


def parse_nowcoder_job(item: dict) -> JobCandidate:
    data = item["data"]
    ext = json.loads(data["ext"])
    description = BeautifulSoup(
        "\n".join(ext.get(key, "") or "" for key in ("infos", "requirements"))
        .replace("\\n", "\n"), "html.parser",
    ).get_text("\n", strip=True)
    if len(description) < 10:
        raise CollectionError("牛客岗位未提供完整职责或任职要求，未计入结果。")
    tags = [item["tag"]["title"] for item in data["pcTagInfo"]["jobInfoTagList"]]
    city_names = {city[0] for city in CITIES.values()}
    cities = list(dict.fromkeys(
        city for tag in tags for city in tag.split("/") if city in city_names
    ))
    city = "/".join(cities)
    education = next((tag for tag in tags if tag in (
        "学历不限", "初中及以下", "中专", "高中", "大专", "本科", "硕士", "博士",
    )), "")
    experience = " / ".join(tag for tag in tags if re.fullmatch(
        r"(?:\d+(?:-\d+)?年(?:以上)?|经验不限|应届生|\d{4}届|\d天/周|最少\d个月)", tag,
    ))
    kind = next(label for code, label, _ in NOWCODER_TYPES.values() if code == data["recruitType"])
    if data["salaryMin"] > 0 and data["salaryMax"] > 0:
        unit = {1: "元/天", 2: "K/月"}[data["salaryType"]]
        salary = f"{data['salaryMin']}-{data['salaryMax']}{unit}"
        if data["salaryType"] == 2 and data["salaryMonth"]:
            salary += f" · {data['salaryMonth']}薪"
    else:
        salary = "薪资面议"
    company = data["recommendInternCompany"]["companyName"]
    return JobCandidate(
        title=data["jobName"], company=company, city=city, salary=salary, source="nowcoder",
        url=f"https://www.nowcoder.com/jobs/detail/{data['id']}",
        education=education, experience=experience, recruitment_type=kind,
        published_at=datetime.fromtimestamp(
            data["refreshTime"] / 1000, tz=timezone(timedelta(hours=8)),
        ).strftime("%Y-%m-%d"),
        description=description,
        raw_text="\n".join([
            data["jobName"], company, city, kind, salary, education, experience, description,
        ]),
    )


def collect_nowcoder(client, request):
    kinds = (
        list(NOWCODER_TYPES) if request.recruitment_type == "all" else [request.recruitment_type]
    )
    city = CITIES[request.city][0]
    jobs, seen = [], set()
    incomplete = 0
    for page in range(1, 6):
        batches, finished = [], []
        for kind in kinds:
            response = client.post(
                "https://www.nowcoder.com/np-api/u/job/square-search",
                data={"requestFrom": 1, "page": page, "pageSize": 20,
                      "recruitType": NOWCODER_TYPES[kind][0], "query": ROLES[request.role][1],
                      "jobCity": json.dumps([city], ensure_ascii=False), "recommend": "false",
                      "order": 0, "pageSource": 5001},
            )
            if response.status_code in (401, 403, 429):
                return jobs, "blocked", "牛客要求登录、安全验证或限制访问，已停止采集。"
            response.raise_for_status()
            result = response.json()
            if result["code"] == 999:
                return jobs, "blocked", "牛客要求登录，请打开原站自行查看岗位。"
            if result["code"] != 0:
                raise CollectionError(f"牛客搜索返回错误：{result.get('msg', result['code'])}")
            data = result["data"]
            batch = []
            for item in data["datas"]:
                try:
                    job = parse_nowcoder_job(item)
                except CollectionError:
                    incomplete += 1
                    continue
                if job.url not in seen and city in job.city.split("/"):
                    seen.add(job.url)
                    batch.append(job)
            batches.append(batch)
            if page >= data["totalPage"] or not batch:
                finished.append(kind)
        jobs.extend(job for row in zip_longest(*batches) for job in row if job is not None)
        kinds = [kind for kind in kinds if kind not in finished]
        if len(jobs) >= request.limit or not kinds:
            break
    reason = f"{incomplete} 个岗位缺少完整 JD，未计入结果。" if incomplete else ""
    return jobs[:request.limit], "partial" if incomplete else "success", reason


def collect_liepin(client, request):
    city = CITIES[request.city]
    url = liepin_search_url(request)
    jobs, seen, errors = [], set(), 0
    status, reason = "success", ""
    with ThreadPoolExecutor(max_workers=4) as pool:
        while url and len(jobs) < request.limit:
            links, next_url = parse_liepin_list(public_page(client, url))
            links = [link for link in links if link not in seen]
            if not links:
                reason = "后续页面没有新的岗位，已停止。"
                break
            seen.update(links)
            for offset in range(0, len(links), 4):
                batch = links[offset : offset + min(4, request.limit - len(jobs))]
                futures = [pool.submit(public_page, client, link) for link in batch]
                for future in futures:
                    try:
                        item = parse_liepin_detail(future.result())
                        if item.city.startswith(city[0]):
                            jobs.append(item)
                    except CollectionBlocked as exc:
                        status, reason = "blocked", str(exc)
                    except (CollectionError, httpx.HTTPError, KeyError, json.JSONDecodeError):
                        errors += 1
                if status == "blocked" or len(jobs) >= request.limit:
                    break
            if status == "blocked":
                break
            url = next_url
    if errors and status == "success":
        status = "partial" if jobs else "error"
        reason = f"{errors} 个详情无法取得完整 JD，未计入结果。"
    if request.role == "ai_application":
        reason += "猎聘使用人工智能分类，结果按简历技能进一步排序。"
    return jobs, status, reason


def collect_zhilian(client, request):
    city = CITIES[request.city]
    jobs, seen = [], set()
    reason = ""
    for page in range(1, 7):
        html = public_page(
            client,
            "https://www.zhaopin.com/jobs/",
            params={
                "jl": city[2],
                "kw": ROLES[request.role][1],
                "p": page,
            },
        )
        items = parse_zhilian(html)
        fresh = [item for item in items if item.url not in seen]
        if not fresh:
            reason = "后续公开页面返回重复岗位，已停止翻页，未重复计数。"
            break
        seen.update(item.url for item in fresh)
        jobs.extend(item for item in fresh if item.city.startswith(city[0]))
        if len(jobs) >= request.limit or not items:
            break
    return jobs[: request.limit], "success", reason


def collect_source(request, source):
    search_urls = source_search_urls(request, source)
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            collector = {
                "liepin": collect_liepin, "zhilian": collect_zhilian, "nowcoder": collect_nowcoder,
            }[source]
            items, status, reason = collector(client, request)
        items = deduplicate(items)
        return items, SourceResult(
            source=source,
            status=status,
            count=len(items),
            message=f"已获取 {len(items)} 个完整岗位（目标上限 {request.limit}）。{reason}",
            search_urls=search_urls,
        )
    except CollectionBlocked as exc:
        return [], SourceResult(
            source=source, status="blocked", count=0, message=str(exc), search_urls=search_urls,
        )
    except (httpx.HTTPError, CollectionError, KeyError, json.JSONDecodeError) as exc:
        return [], SourceResult(
            source=source,
            status="error",
            count=0,
            message=f"{SOURCE_LABELS[source]}采集失败：{exc}",
            search_urls=search_urls,
        )


def collect_jobs(request: CollectionRequest) -> CollectionResult:
    sources = ["liepin", "zhilian"] if request.source == "both" else [request.source]
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        results = list(pool.map(lambda source: collect_source(request, source), sources))
    return CollectionResult(
        jobs=deduplicate([job for jobs, _ in results for job in jobs]),
        sources=[result for _, result in results],
    )
