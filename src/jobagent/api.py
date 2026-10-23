"""HTTP entry point: upload a PDF resume and return structured fields."""

import io
import json
import logging
import wave
from pathlib import Path
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import Response as HTTPResponse
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAIError
from pydantic import ValidationError
from pypdf.errors import PdfReadError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .collectors import collect_jobs
from .config import Settings
from .db import get_session_factory, init_db
from .evaluation import annotate_case, evaluation_summary, human_score, save_case
from .interview import (
    InterviewProvider,
    answer_interview,
    finish_interview,
    get_interview_provider,
    public_session,
    start_interview,
)
from .interview_schemas import AnswerInput, StartInterview
from .job_catalog import CITY_OPTIONS, ROLE_OPTIONS
from .job_input import manual_job, read_job_file
from .match_schemas import (
    CollectionRequest,
    CollectionResult,
    HumanAnnotation,
    JobCandidate,
    MatchReport,
    MatchRequest,
    RankedJob,
    RankRequest,
)
from .matching import RUBRIC, RUBRIC_VERSION, MatchProvider, get_match_provider
from .models import InterviewSession, MatchCase
from .ranking import rank_jobs
from .resume import OpenAIResumeProvider, extract_pdf_text, get_resume_provider
from .schemas import ResumeExtraction
from .uploads import MAX_AUDIO_BYTES, MAX_PDF_BYTES, UploadTooLarge, read_limited

app = FastAPI(title="Jobagent", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


def database_session():
    init_db()
    with get_session_factory()() as session:
        yield session


Database = Annotated[Session, Depends(database_session)]
Interviewer = Annotated[InterviewProvider, Depends(get_interview_provider)]


def required_interview(session: Session, interview_id: str) -> InterviewSession:
    record = session.get(InterviewSession, interview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="该面试记录不存在。")
    return record


@app.post("/interviews")
def create_interview(request: StartInterview, provider: Interviewer, session: Database) -> dict:
    try:
        record = start_interview(request, provider)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="面试计划格式不正确，请重新开始。") from exc
    session.add(record)
    session.commit()
    return public_session(record)


@app.get("/interviews/{interview_id}")
def read_interview(interview_id: str, session: Database) -> dict:
    return public_session(required_interview(session, interview_id))


@app.post("/interviews/{interview_id}/answers")
def interview_answer(
    interview_id: str,
    request: AnswerInput,
    provider: Interviewer,
    session: Database,
) -> dict:
    record = required_interview(session, interview_id)
    if record.state["status"] != "active":
        raise HTTPException(status_code=409, detail="面试已结束，请开始新的面试。")
    if not request.answer.strip():
        raise HTTPException(status_code=422, detail="请填写回答后再提交。")
    try:
        record.state = answer_interview(record.state, request.answer.strip(), provider)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="面试评估格式不正确，回答尚未提交。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"面试评估失败：{exc}") from exc
    session.commit()
    return public_session(record)


@app.post("/interviews/{interview_id}/finish")
def end_interview(interview_id: str, session: Database) -> dict:
    record = required_interview(session, interview_id)
    if record.state["status"] == "active":
        record.state = finish_interview(json.loads(json.dumps(record.state)))
        session.commit()
    return public_session(record)


@app.post("/interviews/{interview_id}/audio")
def interview_audio(
    interview_id: str,
    file: UploadFile,
    provider: Interviewer,
    session: Database,
) -> dict:
    record = required_interview(session, interview_id)
    if record.state["status"] != "active":
        raise HTTPException(status_code=409, detail="面试已结束，请开始新的面试。")
    try:
        audio = read_limited(file.file, MAX_AUDIO_BYTES, "录音文件")
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    try:
        with wave.open(io.BytesIO(audio)) as recording:
            if recording.getnframes() == 0:
                raise ValueError("录音为空，请重新录制。")
    except (wave.Error, EOFError) as exc:
        raise HTTPException(
            status_code=422, detail="录音不是有效的 WAV 音频，请重新录制。"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        record.state = answer_interview(record.state, audio, provider)
    except ValidationError as exc:
        raise HTTPException(status_code=502, detail="语音评估格式不正确，录音尚未提交。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"语音评估失败：{exc}") from exc
    session.commit()
    return public_session(record)


@app.get("/jobs/options")
def job_options() -> dict:
    return {
        "roles": [
            {key: item[key] for key in ("id", "label", "group", "keyword")} for item in ROLE_OPTIONS
        ],
        "cities": [
            {key: item[key] for key in ("id", "label", "group", "pinyin", "hot")}
            for item in CITY_OPTIONS
        ],
    }


@app.post("/jobs/collect", response_model=CollectionResult)
def collect(request: CollectionRequest) -> CollectionResult:
    return collect_jobs(request)


@app.post("/jobs/rank", response_model=list[RankedJob])
def rank_collected_jobs(request: RankRequest) -> list[RankedJob]:
    return rank_jobs(request)


@app.post("/jobs/upload", response_model=JobCandidate)
def upload_job(
    file: UploadFile | None = None,
    text: Annotated[str, Form()] = "",
    title: Annotated[str, Form()] = "",
) -> JobCandidate:
    if file is not None and text.strip():
        raise HTTPException(status_code=422, detail="上传文件与粘贴文字请选择其中一种。")
    try:
        if file is not None:
            text = read_job_file(file.file, file.filename or "")
        return manual_job(text, title)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/matching/rubric")
def rubric() -> dict:
    return {
        "version": RUBRIC_VERSION,
        "dimensions": [
            {"category": key, "label": value[0], "weight": value[1]}
            for key, value in RUBRIC.items()
        ],
        "rule": "命中=1，部分命中=0.5，简历未体现=0；硬性要求权重1，加分项权重0.5。"
        "先计算各维度加权满足率，再按维度权重合成100分。JD未要求的维度排除后重新归一。",
        "gap_rule": "技能类要求中的部分命中与简历未体现都算 gap；采用统一技能名称精确比较。",
    }


@app.post("/matches", response_model=MatchReport)
def match(
    request: MatchRequest,
    provider: Annotated[MatchProvider, Depends(get_match_provider)],
    session: Database,
) -> MatchReport:
    try:
        report = provider.match(request)
    except ValidationError as exc:
        reasons = []
        for error in exc.errors(include_input=False, include_url=False):
            location = error["loc"]
            prefix = (
                f"第{location[1] + 1}项要求："
                if (len(location) > 1 and location[0] == "requirements")
                else ""
            )
            reasons.append(prefix + error["msg"].removeprefix("Value error, "))
        raise HTTPException(
            status_code=502, detail="匹配报告格式不正确：" + "；".join(reasons)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"匹配证据核对失败：{exc}") from exc
    save_case(session, request, report)
    return report


@app.get("/evaluation", include_in_schema=False)
def evaluation_page() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "evaluation.html")


@app.get("/evaluation/summary")
def metrics(session: Database) -> dict:
    return evaluation_summary(session)


@app.get("/evaluation/cases")
def cases(session: Database) -> list[dict]:
    records = session.scalars(select(MatchCase).order_by(MatchCase.created_at.desc())).all()
    return [
        {
            "case_id": record.id,
            "title": record.job_data["title"],
            "company": record.job_data["company"],
            "name": record.resume_data["name"],
            "labelled": record.annotation is not None,
        }
        for record in records
    ]


def required_case(session: Session, case_id: str) -> MatchCase:
    record = session.get(MatchCase, case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="这组简历与岗位配对不存在。")
    return record


@app.get("/evaluation/cases/{case_id}")
def blind_case(case_id: str, session: Database) -> dict:
    record = required_case(session, case_id)
    # No model score, predicted gaps, or generated rubric decisions in the annotation view.
    return {
        "case_id": record.id,
        "resume": record.resume_data,
        "job": record.job_data,
        "annotation": record.annotation,
    }


@app.put("/evaluation/cases/{case_id}/annotation")
def annotate(case_id: str, annotation: HumanAnnotation, session: Database) -> dict:
    record = required_case(session, case_id)
    annotate_case(session, record, annotation)
    return {"saved": True, "human_score": human_score(annotation)}


@app.get("/evaluation/export")
def export_cases(session: Database) -> HTTPResponse:
    records = session.scalars(select(MatchCase).order_by(MatchCase.id)).all()
    lines = [
        json.dumps(
            {
                "pair_id": record.id,
                "resume": record.resume_data,
                "job": record.job_data,
                "prediction": record.prediction,
                "annotation": record.annotation,
            },
            ensure_ascii=False,
        )
        for record in records
    ]
    return HTTPResponse(
        content="\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="match-evaluation.jsonl"'},
    )


@app.exception_handler(OpenAIError)
def model_error(_request: Request, exc: OpenAIError) -> JSONResponse:
    settings = Settings()
    status = 502
    if not settings.llm_api_key.strip():
        status = 503
        message = "尚未配置模型密钥。请在项目 .env 中填写 JOBAGENT_LLM_API_KEY 后重新解析。"
    elif isinstance(exc, APITimeoutError):
        message = "模型响应超时，请稍后重新解析。"
    elif isinstance(exc, APIConnectionError):
        message = "无法连接模型服务，请检查网络、代理和模型接口地址。"
    elif isinstance(exc, APIStatusError):
        reasons = {
            400: "模型请求参数不被接受",
            401: "模型密钥无效或已过期",
            403: "没有该模型的访问权限",
            404: "模型名称或接口地址不存在",
            429: "模型调用额度不足或请求过于频繁",
        }
        reason = reasons.get(exc.status_code, "模型服务返回错误")
        body = exc.body
        if isinstance(body, dict):
            body = body.get("error", body)
        detail = body.get("message", exc.message) if isinstance(body, dict) else str(body)
        detail = detail.replace(settings.llm_api_key, "[已隐藏]")
        message = f"{reason}（{exc.status_code}）：{detail}"
    else:
        message = "模型客户端配置错误，请检查接口地址和密钥。"
    return JSONResponse(status_code=status, content={"detail": message})


@app.post("/resumes/parse", response_model=ResumeExtraction, summary="上传 PDF 并解析简历")
def parse_resume(
    file: UploadFile,
    provider: Annotated[OpenAIResumeProvider, Depends(get_resume_provider)],
) -> ResumeExtraction:
    started = perf_counter()
    try:
        data = read_limited(file.file, MAX_PDF_BYTES, "简历 PDF")
        text = extract_pdf_text(io.BytesIO(data))
        logging.getLogger("uvicorn.error").info(
            "resume_pdf_extracted elapsed_seconds=%.3f bytes=%d text_chars=%d",
            perf_counter() - started,
            len(data),
            len(text),
        )
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except PdfReadError as exc:
        raise HTTPException(
            status_code=422, detail="无法读取 PDF，文件可能已损坏、已加密或并非有效的 PDF。"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return provider.extract(text)
    except ValidationError as exc:
        errors = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '返回内容'}：{error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise HTTPException(status_code=502, detail=f"模型返回的数据格式不正确：{errors}") from exc
