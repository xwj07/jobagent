import pytest
from pydantic import ValidationError

from jobagent.llm import MockProvider, OpenAIChatProvider, ProviderError
from jobagent.schemas import JobExtraction, SkillMention

JD = """【AI应用工程师】
杭州 - 3-5年 - 本科
25-40K·14薪
熟悉 Python、FastAPI，有 RAG 经验；熟悉 Kubernetes 者优先。
"""


def test_mock_extracts_basic_fields():
    result = MockProvider().extract(JD, company="Acme")
    assert result.city == "杭州"
    assert result.salary_min_k == 25
    assert result.salary_max_k == 40
    assert result.years_min == 3
    assert result.education == "本科"
    assert result.company == "Acme"


def test_mock_skill_required_flag():
    result = MockProvider().extract(JD)
    by_name = {s.name: s.required for s in result.skills}
    assert by_name["Python"] is True
    assert by_name["RAG"] is True
    # "优先" appears near Kubernetes -> not required
    assert by_name["Kubernetes"] is False


def test_mock_rejects_too_short_input():
    with pytest.raises(ProviderError):
        MockProvider().extract("short")


def test_mock_handles_nan_style_salary():
    result = MockProvider().extract("【岗位】\n北京 · 面议\nPython 开发。", company="X")
    assert result.salary_min_k is None and result.salary_max_k is None


def test_salary_order_is_fixed():
    result = JobExtraction(salary_min_k=40, salary_max_k=20)
    assert (result.salary_min_k, result.salary_max_k) == (20, 40)


def test_salary_range_validation():
    with pytest.raises(ValidationError):
        JobExtraction(salary_min_k=5000)


class _StubResponse:
    def __init__(self, content: str):
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        self.choices = [choice]


class _FlakyClient:
    """Fails validation once, then succeeds. Verifies feedback-retry behaviour."""

    def __init__(self, bad: str, good: str):
        self.calls = 0
        self.bad = bad
        self.good = good
        self.chat = self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.calls += 1
        return _StubResponse(self.bad if self.calls == 1 else self.good)


def test_provider_retries_with_validation_feedback():
    good = (
        '{"title":"AI工程师","company":"X","city":"杭州","salary_min_k":20,'
        '"salary_max_k":30,"years_min":2,"education":"本科",'
        '"skills":[{"name":"Python","required":true}]}'
    )
    client = _FlakyClient(bad='{"salary_min_k": "not-a-number"}', good=good)
    provider = OpenAIChatProvider(client=client, max_retries=3)
    result = provider.extract(JD)
    assert result.title == "AI工程师"
    assert client.calls == 2


def test_provider_gives_up_after_retries():
    # "{}" is a *valid* extraction (all defaults), so it would not trigger a retry;
    # use schema-violating output instead.
    invalid = '{"salary_min_k": "not-a-number"}'
    client = _FlakyClient(bad=invalid, good=invalid)
    provider = OpenAIChatProvider(client=client, max_retries=2)
    with pytest.raises(ProviderError):
        provider.extract(JD)
    assert client.calls == 2


def test_schema_hint_does_not_crash():
    assert JobExtraction(skills=[SkillMention(name="RAG")]).skills[0].required is True
