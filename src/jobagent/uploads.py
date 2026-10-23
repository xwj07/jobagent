"""Size limits for every user-supplied input.

Why this module exists: FastAPI spools uploads to disk before our code runs, so a
huge file costs disk and, if we call ``read()`` with no argument, memory too. Each
reader here asks for at most ``limit + 1`` bytes. If it gets more than ``limit``, it
stops and reports the file as too large, without loading the rest.
"""

from typing import BinaryIO

MB = 1024 * 1024

MAX_PDF_BYTES = 10 * MB
MAX_TXT_BYTES = 2 * MB
MAX_AUDIO_BYTES = 10 * MB
MAX_JOB_TEXT_CHARS = 20_000


class UploadTooLarge(ValueError):
    """Raised when an input exceeds its limit.

    Subclasses ValueError so existing 422 handlers still work. API endpoints catch it
    before the ValueError handler and return 413 instead.
    """

    def __init__(self, label: str, limit: int) -> None:
        self.label = label
        self.limit = limit
        super().__init__(f"{label}超过 {limit // MB} MB 上限，请压缩或裁剪后再上传。")


def read_limited(stream: BinaryIO, limit: int, label: str) -> bytes:
    """Read the whole stream, but never more than ``limit`` bytes."""
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise UploadTooLarge(label, limit)
    return data
