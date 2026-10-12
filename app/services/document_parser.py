import re

import fitz


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
