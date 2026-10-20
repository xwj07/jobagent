import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobagent.db import Base
from jobagent.extract import content_hash, ingest_many
from jobagent.llm import MockProvider
from jobagent.schemas import RawPosting
from jobagent.stats import corpus_summary, salary_summary, skill_frequency


@pytest.fixture()
def factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _posting(**overrides) -> RawPosting:
    data = {
        "raw_text": (
            "【AI应用工程师】\n杭州 · 3-5年 · 本科\n25-40K\n"
            "Python、FastAPI、RAG，熟悉 Kubernetes 者优先。"
        ),
        "company": "Acme",
        "title": "AI应用工程师",
    }
    data.update(overrides)
    return RawPosting(**data)


def test_ingest_and_stats(factory):
    result = ingest_many(factory, [_posting()], MockProvider())
    assert result.inserted == 1
    assert result.skipped == 0

    with factory() as session:
        rows = skill_frequency(session)
        names = {r["skill"] for r in rows}
        assert {"python", "fastapi", "rag", "kubernetes"} <= names
        summary = corpus_summary(session)
        assert summary["postings"] == 1


def test_reingest_is_idempotent(factory):
    ingest_many(factory, [_posting()], MockProvider())
    result = ingest_many(factory, [_posting()], MockProvider())
    assert result.inserted == 0
    assert result.skipped == 1


def test_hash_ignores_whitespace_noise():
    a = content_hash("Python  开发\n\n要求", "Acme", "工程师")
    b = content_hash("python 开发 要求", "Acme", "工程师")
    assert a == b


def test_alias_merge_within_posting(factory):
    text = "职位：AI 工程师\n熟悉 k8s 与 Kubernetes，都会加分。"
    ingest_many(factory, [_posting(raw_text=text)], MockProvider())
    with factory() as session:
        rows = skill_frequency(session)
        k8s_rows = [r for r in rows if r["skill"] in ("kubernetes", "k8s")]
        assert len(k8s_rows) == 1
        assert k8s_rows[0]["postings"] == 1


def test_salary_median(factory):
    p1 = _posting(raw_text="职位A 杭州 20-30K 要求 Python 开发经验")
    p2 = _posting(raw_text="职位B 北京 40-60K 要求 Java 开发经验", title="后端")
    ingest_many(factory, [p1, p2], MockProvider())
    with factory() as session:
        s = salary_summary(session)
        assert s["postings_with_salary"] == 2
        assert s["median_monthly_k"] == 37.5


def test_failure_is_isolated(factory):
    # Passes input validation but MockProvider refuses it (too short after strip).
    bad = _posting(raw_text="   x   \n\n  ")
    good = _posting()
    result = ingest_many(factory, [bad, good], MockProvider())
    assert result.inserted == 1
    assert len(result.failed) == 1
