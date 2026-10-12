from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.document_parser import DocumentParseError
from app.services.document_repository import DocumentRepository
from app.services.document_upload import (
    UploadValidationError,
    process_upload,
)


router = APIRouter(
    prefix="/documents",
    tags=["Document Upload"],
)

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/upload", status_code=201)
async def upload_document(
    db: DbDep,
    file: UploadFile = File(...),
):
    try:
        upload_data = await process_upload(file)

        repository = DocumentRepository(db)
        document = repository.create_uploaded(upload_data)

        return {
            "id": document.id,
            "file_id": document.file_id,
            "filename": document.filename,
            "media_type": document.media_type,
            "file_size": document.file_size,
            "content_hash": document.content_hash,
            "parse_status": document.parse_status,
            "text_length": document.text_length,
        }

    except UploadValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    except DocumentParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    finally:
        await file.close()
