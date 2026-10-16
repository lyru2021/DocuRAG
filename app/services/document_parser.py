"""TXT/PDF 文本解析服务。

解析结果会作为后续分块、页码映射和 evidence 校验的来源。
"""

import re
from dataclasses import dataclass

import fitz


class DocumentParseError(Exception):
    """Raised when document text extraction fails.

    文档无法解析或解析后没有可用文本时抛出。
    """


def clean_text(text: str) -> str:
    """清理解析器返回的原始文本。

    Args:
        text: TXT 解码结果或 PDF 页面提取文本。

    Returns:
        str: 规范化换行、空白和空字符后的文本。

    Notes:
        清理策略会保留段落分隔，避免破坏后续 chunk 的字符偏移语义。
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = text.replace("\x00", "")

    text = re.sub(r"[^\S\n]+", " ", text)

    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_txt(data: bytes) -> str:
    """解析 UTF-8 文本文件。

    Args:
        data: 上传文件的原始字节。

    Returns:
        str: 清理后的文本内容。

    Raises:
        DocumentParseError: 文件不是 UTF-8 编码，或清理后没有可读文本。
    """

    try:
        # 必须能够按 UTF-8 解码，否则调用方无法可靠保存文本偏移。
        text = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentParseError(
            "TXT file must use UTF-8 encoding."
        ) from exc

    text = clean_text(text)

    if not text:
        raise DocumentParseError(
            "TXT file contains no readable text."
        )

    return text


def parse_pdf(data: bytes) -> str:
    """解析 PDF 并返回合并后的纯文本。

    Args:
        data: PDF 原始字节。

    Returns:
        str: 按页面顺序合并后的文本。

    Raises:
        DocumentParseError: PDF 无法打开、无法解析，或没有可提取文本。
    """

    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            pages = []

            for page in pdf:
                page_text = page.get_text("text", sort=True)
                page_text = clean_text(page_text)

                if page_text:
                    pages.append(page_text)

            text = "\n\n".join(pages)

    except Exception as exc:
        raise DocumentParseError(
            "PDF could not be opened or parsed."
        ) from exc

    if not text:
        raise DocumentParseError(
            "No extractable text found. "
            "Scanned PDFs require OCR, which is not supported."
        )

    return text


@dataclass(frozen=True)
class ParsedPage:
    """PDF 单页文本及其在合并全文中的字符区间。"""

    page_number: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class ParsedPDF:
    """带页面映射信息的 PDF 解析结果。"""

    text: str
    pages: list[ParsedPage]


def parse_pdf_with_pages(data: bytes) -> ParsedPDF:
    """解析 PDF 并保留页面到合并全文的映射。

    Args:
        data: PDF 原始字节。

    Returns:
        ParsedPDF: 合并文本和每页文本区间。

    Raises:
        DocumentParseError: PDF 无法打开、无法解析，或没有可提取文本。

    Notes:
        页面之间用两个换行连接，因此每个页面的 `start_char/end_char`
        必须跟最终 `text` 的字符位置同步推进。
    """

    pages: list[ParsedPage] = []
    text_parts: list[str] = []
    cursor = 0

    try:
        with fitz.open(stream=data, filename="pdf") as pdf:
            for page_number, page in enumerate(pdf, start=1):
                page_text = clean_text(
                    page.get_text("text", sort=True)
                )

                if not page_text:
                    continue

                if text_parts:
                    text_parts.append("\n\n")
                    cursor += 2

                start = cursor
                end = start + len(page_text)

                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=page_text,
                        start_char=start,
                        end_char=end,
                    )
                )

                text_parts.append(page_text)
                cursor = end

    except Exception as exc:
        raise DocumentParseError(
            "PDF could not be opened or parsed."
        ) from exc

    full_text = "".join(text_parts)

    if not full_text:
        raise DocumentParseError(
            "No extractable text found. "
            "Scanned PDFs require OCR, which is not supported."
        )

    return ParsedPDF(
        text=full_text,
        pages=pages,
    )
