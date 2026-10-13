import re

import fitz
from dataclasses import dataclass

class DocumentParseError(Exception):
    """Raised when document text extraction fails."""


def clean_text(text: str) -> str:

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = text.replace("\x00", "")

    text = re.sub(r"[^\S\n]+", " ", text)

    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def parse_txt(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig", errors="strict")    #必须能够按UTF-8解码，否则抛出异常
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
    page_number: int
    text: str
    start_char: int
    end_char: int

@dataclass(frozen=True)
class ParsedPDF:
    text: str
    pages: list[ParsedPage]

def parse_pdf_with_pages(data: bytes) -> ParsedPDF:

    pages: list[ParsedPage] = []
    text_parts: list[str] = []
    cursor = 0

    try:
        with fitz.open(stream = data, filename = "pdf") as pdf:
            for page_number, page in enumerate(pdf, start = 1):
                page_text = clean_text(
                    page.get_text("text", sort = True)
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
                        page_number = page_number,
                        text = page_text,
                        start_char = start,
                        end_char = end
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