import hashlib
from pathlib import Path

from fastapi import UploadFile

from app.services.document_parser import DocumentParseError, parse_pdf_with_pages, parse_txt

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
READ_CHUNK_SIZE = 1024 * 1024  # 1 MB

SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}

class UploadValidationError(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code

async def process_upload(file: UploadFile) -> dict:
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
            raise UploadValidationError("File exceeds the maximum limit of 10 MB.", 413)
        
        content.extend(chunk)

    if not content:
        raise UploadValidationError("Uploaded file is empty.", 400)
    data = bytes(content)

    if extension == ".pdf":
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
    }