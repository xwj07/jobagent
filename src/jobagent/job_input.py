"""User-supplied job descriptions share the same matching contract as collected jobs."""

import io
from pathlib import Path
from typing import BinaryIO

from pypdf.errors import PdfReadError

from .match_schemas import JobCandidate
from .resume import extract_pdf_text
from .uploads import (
    MAX_JOB_TEXT_CHARS,
    MAX_PDF_BYTES,
    MAX_TXT_BYTES,
    read_limited,
)


def read_job_file(stream: BinaryIO, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        data = read_limited(stream, MAX_PDF_BYTES, "招聘 PDF")
        try:
            return extract_pdf_text(io.BytesIO(data))
        except PdfReadError as exc:
            raise ValueError("无法读取招聘 PDF，请确认文件有效且未加密。") from exc
    if suffix == ".txt":
        data = read_limited(stream, MAX_TXT_BYTES, "招聘 TXT")
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT 文件不是 UTF-8 编码，请另存为 UTF-8 后上传。") from exc
    raise ValueError("招聘信息文件仅支持 PDF 或 TXT（UTF-8）。")


def manual_job(text: str, title: str) -> JobCandidate:
    text = text.strip()
    if len(text) > MAX_JOB_TEXT_CHARS:
        raise ValueError(
            f"招聘信息超过 {MAX_JOB_TEXT_CHARS} 字符，请只粘贴岗位描述与要求部分。"
        )
    if len(text) < 10:
        raise ValueError("招聘信息过短，请提供至少 10 个字符的岗位描述和要求。")
    return JobCandidate(
        title=title.strip() or "自定义岗位",
        company="",
        city="",
        salary="",
        source="manual",
        url=None,
        raw_text=text,
        description=text,
    )
