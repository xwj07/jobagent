"""LLM providers. Two implementations behind one Protocol so the rest of the code never
knows whether an extraction came from a real model or from deterministic rules.

Design notes
------------
* The schema lives in ``schemas.JobExtraction``. The provider returns a validated
  instance or raises ``ProviderError``; callers never see raw JSON strings.
* Retries are split in two: transport errors (timeouts, 5xx) are retried as-is, while
  validation errors are retried *with feedback* — the model is told exactly which
  field failed. This is the cheapest reliability win you can build.
* The mock provider is not a toy: it powers the test suite and lets the whole pipeline
  run without an API key, which is why CI needs no secrets.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from pydantic import ValidationError

from .config import settings
from .schemas import JobExtraction, SkillMention

SYSTEM_PROMPT = """你是一个招聘信息结构化抽取器。用户会给出一段职位描述（JD），\
你只输出一个 JSON 对象，不要输出任何解释、Markdown 或代码块。

字段定义：
- title: 岗位名称，如 "AI应用工程师"
- company: 公司名称；未知填 "unknown"
- city: 工作城市（中文），未知填 null
- salary_min_k / salary_max_k: 月薪下限/上限，单位千元人民币，整数；
  例如 "25-40K·14薪" 输出 25 和 40；"面议" 输出 null；年薪须除以 12 再换算
- years_min: 最低工作年限，整数；"3-5年" 输出 3，"不限" 输出 0，未提及 output null
- education: 学历要求，取以下之一：不限/大专/本科/硕士/博士；未提及填 null
- skills: 技术技能数组，每项 {"name": 技能名, "required": 是否硬性要求}
  只抽取技术、工具、框架、语言、领域能力；"加分项/优先" 标 required=false。
  技能名用业界通用写法（如 Kubernetes、PostgreSQL、RAG），不要抽取软技能。

示例输出：
{"title":"AI应用工程师","company":"某科技公司","city":"杭州","salary_min_k":25,\
"salary_max_k":45,"years_min":3,"education":"本科",\
"skills":[{"name":"Python","required":true},{"name":"RAG","required":true},\
{"name":"LangChain","required":false}]}"""


class ProviderError(RuntimeError):
    """Raised when a posting could not be extracted after all retries."""


class Provider(Protocol):
    def extract(
        self, raw_text: str, *, company: str | None = None, title: str | None = None
    ) -> JobExtraction: ...


def _schema_hint() -> str:
    return json.dumps(JobExtraction.model_json_schema(), ensure_ascii=False)


class OpenAIChatProvider:
    """Works with any OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        json_mode: bool = True,
        max_retries: int = 3,
        client=None,
    ) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI(
                base_url=base_url or settings.llm_base_url,
                api_key=api_key or settings.llm_api_key or "EMPTY",
            )
        self.client = client
        self.model = model or settings.llm_model
        self.json_mode = json_mode
        self.max_retries = max_retries

    def extract(
        self, raw_text: str, *, company: str | None = None, title: str | None = None
    ) -> JobExtraction:
        hints = []
        if title:
            hints.append(f"岗位名称提示：{title}")
        if company:
            hints.append(f"公司名称提示：{company}")
        user = ("\n".join(hints) + "\n\n" if hints else "") + "职位描述：\n" + raw_text

        last_error: Exception | None = None
        for _attempt in range(1, self.max_retries + 1):
            feedback = ""
            if isinstance(last_error, ValidationError):
                feedback = (
                    "\n\n上一次输出未通过校验，请修正以下问题后重新输出完整 JSON：\n"
                    + str(last_error)
                )
            elif last_error is not None:
                feedback = "\n\n上一次请求失败，请重新输出完整 JSON。"

            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT + feedback},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"} if self.json_mode else None,
                )
                content = resp.choices[0].message.content or ""
                return JobExtraction.model_validate_json(content)
            except ValidationError as exc:  # malformed or schema-violating output
                last_error = exc
            except Exception as exc:  # transport / API errors from the SDK
                last_error = exc

        raise ProviderError(f"extraction failed after {self.max_retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

# Vocabulary for rule-based extraction. Extended, not replaced, by the LLM path.
_SKILL_VOCAB: dict[str, str] = {
    "python": "Python",
    "java": "Java",
    "go": "Go",
    "golang": "Go",
    "c++": "C++",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "redis": "Redis",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "elasticsearch": "Elasticsearch",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "llamaindex": "LlamaIndex",
    "rag": "RAG",
    "大模型": "大语言模型",
    "llm": "大语言模型",
    "agent": "Agent",
    "智能体": "Agent",
    "向量数据库": "向量数据库",
    "pgvector": "pgvector",
    "milvus": "Milvus",
    "embedding": "Embedding",
    "prompt": "提示词工程",
    "微调": "微调",
    "机器学习": "机器学习",
    "深度学习": "深度学习",
    "pytorch": "PyTorch",
    "transformer": "Transformer",
    "git": "Git",
    "linux": "Linux",
}

_NON_REQUIRED_RE = re.compile(r"加分项|优先|bonus|plus", re.IGNORECASE)
_CLAUSE_SPLIT_RE = re.compile(r"[\n。；;]")


def _is_optional(text: str, needle: str) -> bool:
    """True if the clause mentioning ``needle`` is phrased as a nice-to-have."""
    for clause in _CLAUSE_SPLIT_RE.split(text):
        if needle in clause:
            return _NON_REQUIRED_RE.search(clause) is not None
    return False


def _find_salary(text: str) -> tuple[int | None, int | None]:
    # "25-40K", "25~40k·14薪", "30K以下"
    m = re.search(r"(\d{1,3})\s*[-~－至]\s*(\d{1,3})\s*[kK]", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,3})\s*[kK]\s*以下", text)
    if m:
        return None, int(m.group(1))
    # Annual salary in 万: "30-50万/年"
    m = re.search(r"(\d{1,3})\s*[-~－至]\s*(\d{1,3})\s*万", text)
    if m:
        lo, hi = int(m.group(1)) * 10 // 12, int(m.group(2)) * 10 // 12
        return lo, hi
    return None, None


def _find_years(text: str) -> int | None:
    if re.search(r"(不限|无经验)", text):
        return 0
    m = re.search(r"(\d{1,2})\s*[-~－至]?\s*\d*\s*年(以上|及以上)?", text)
    if m:
        return int(m.group(1))
    return None


def _find_education(text: str) -> str | None:
    for level in ("博士", "硕士", "本科", "大专"):
        if level in text:
            return level
    if "不限" in text and "学历" in text:
        return "不限"
    return None


class MockProvider:
    """Deterministic, dependency-free extractor used by tests and ``--provider mock``."""

    def extract(
        self, raw_text: str, *, company: str | None = None, title: str | None = None
    ) -> JobExtraction:
        if not raw_text or len(raw_text.strip()) < 10:
            raise ProviderError("raw_text too short")

        lower = raw_text.lower()
        skills: list[SkillMention] = []
        seen: set[str] = set()
        for needle, display in _SKILL_VOCAB.items():
            if display.lower() in seen:
                continue
            if needle.isascii():
                pattern = rf"(?<![a-z0-9+]){re.escape(needle)}(?![a-z0-9+])"
                hit = re.search(pattern, lower) is not None
            else:
                hit = needle in lower
            if not hit:
                continue
            seen.add(display.lower())
            # Required-ness is judged per clause, not per character window: a fixed
            # window bleeds into neighbouring sentences ("RAG 经验；Kubernetes 优先"
            # would wrongly mark RAG as optional).
            required = not _is_optional(lower, needle)
            skills.append(SkillMention(name=display, required=required))

        salary_min, salary_max = _find_salary(raw_text)
        heading = title or _first_line_title(raw_text)
        return JobExtraction(
            title=heading or "unknown",
            company=company or "unknown",
            city=_find_city(raw_text),
            salary_min_k=salary_min,
            salary_max_k=salary_max,
            years_min=_find_years(raw_text),
            education=_find_education(raw_text),
            skills=skills,
        )


_CITIES = ("北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉", "西安", "苏州", "长沙")


def _find_city(text: str) -> str | None:
    for city in _CITIES:
        if city in text:
            return city
    return None


def _first_line_title(text: str) -> str | None:
    first = text.strip().splitlines()[0].strip("【】[] ")
    return first[:60] if first else None


def get_provider(name: str | None = None) -> Provider:
    name = (name or settings.provider).lower()
    if name == "mock":
        return MockProvider()
    if name == "openai":
        return OpenAIChatProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            json_mode=settings.json_mode,
            max_retries=settings.max_retries,
        )
    raise ValueError(f"unknown provider: {name!r} (use 'mock' or 'openai')")
