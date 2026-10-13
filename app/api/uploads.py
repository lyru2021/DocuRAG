from typing import Annotated
from fastapi import APIRouter, Depends,File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.services.file_storage import LocalFileStorage
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
        storage = LocalFileStorage(Path(get_settings().UPLOAD_DIR))
        file_id = str(uuid4())

        upload_data["file_id"] = file_id

        saved_pdf = False

        try:
            raw_pdf = upload_data.get("raw_pdf")

            if raw_pdf is not None:
                storage.save_pdf(file_id, raw_pdf)
                saved_pdf = True

            document = DocumentRepository(db).create_uploaded(
                upload_data
            )

        except Exception:
            if saved_pdf:
                storage.delete_pdf(file_id)
            raise


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
