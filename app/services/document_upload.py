"""上传文件校验与解析编排服务。

将 FastAPI 的 `UploadFile` 转换为仓储层可持久化的数据字典。
"""

import hashlib
from pathlib import Path

from fastapi import UploadFile

from app.services.document_parser import (
    DocumentParseError,
    parse_pdf_with_pages,
    parse_txt,
)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
READ_CHUNK_SIZE = 1024 * 1024  # 1 MB

SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


class UploadValidationError(Exception):
    """上传请求不满足业务校验时抛出的异常。

    Args:
        message: 返回给 API 调用方的错误说明。
        status_code: 对应的 HTTP 状态码。
    """

    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code


async def process_upload(file: UploadFile) -> dict:
    """校验上传文件并提取可入库的文档数据。

    Args:
        file: FastAPI 接收到的上传文件对象。

    Returns:
        dict: 供仓储层创建文档的数据，包括文本、hash、文件大小和 PDF 页面映射。

    Raises:
        UploadValidationError: 文件名、扩展名、大小或 PDF 签名不符合要求。
        DocumentParseError: TXT/PDF 内容无法解析出有效文本。
    """

    filename = file.filename or ""

    if not filename:
        raise UploadValidationError("Filename is required", 400)

    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise UploadValidationError("Only PDF and TXT files are supported.", 415)

    content = bytearray()

    while True:
        chunk = await file.read(READ_CHUNK_SIZE)

        if not chunk:
            break

        if len(content) + len(chunk) > MAX_FILE_SIZE:
            raise UploadValidationError(
                "File exceeds the maximum limit of 10 MB.",
                413,
            )

        content.extend(chunk)

    if not content:
        raise UploadValidationError("Uploaded file is empty.", 400)

    data = bytes(content)

    if extension == ".pdf":
        # 这里只做快速签名检查，真正的 PDF 结构校验交给 PyMuPDF 完成。
        if not data.startswith(b"%PDF-"):
            raise UploadValidationError("Invalid PDF file signature.", 415)

        parsed = parse_pdf_with_pages(data)
        text = parsed.text

        pages = [
            {
                "page_number": page.page_number,
                "content": page.text,
                "start_char": page.start_char,
                "end_char": page.end_char,
            }
            for page in parsed.pages
        ]
    else:
        text = parse_txt(data)
        pages = []

    return {
        "filename": filename,
        "media_type": SUPPORTED_EXTENSIONS[extension],
        "text": text,
        "text_length": len(text),
        "file_size": len(data),
        "content_hash": hashlib.sha256(data).hexdigest(),
        "pages": pages,
        "raw_pdf": data if extension == ".pdf" else None,
    }
