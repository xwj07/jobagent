"""User-supplied job descriptions share the same matching contract as collected jobs."""

from pathlib import Path
from typing import BinaryIO

from pypdf.errors import PdfReadError

from .match_schemas import JobCandidate
from .resume import extract_pdf_text


def read_job_file(stream: BinaryIO, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            return extract_pdf_text(stream)
        except PdfReadError as exc:
            raise ValueError("无法读取招聘 PDF，请确认文件有效且未加密。") from exc
    if suffix == ".txt":
        try:
            return stream.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("TXT 文件不是 UTF-8 编码，请另存为 UTF-8 后上传。") from exc
    raise ValueError("招聘信息文件仅支持 PDF 或 TXT（UTF-8）。")


def manual_job(text: str, title: str) -> JobCandidate:
    text = text.strip()
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
    )
