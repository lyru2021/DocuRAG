from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage
from app.schemas.document import DocumentCreate


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: DocumentCreate) -> Document:
        document = Document(
            title=data.title,
            filename=data.filename,
        )

        try:
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
        except Exception:
            self.db.rollback()
            raise

        return document

    def list_all(self) -> list[Document]:
        statement = select(Document).order_by(Document.id)

        return list(
            self.db.scalars(statement).all()
        )

    def get(self, document_id: int) -> Document | None:
        return self.db.get(Document, document_id)

    def delete(self, document_id: int) -> bool:
        document = self.get(document_id)

        if document is None:
            return False

        try:
            self.db.delete(document)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return True

    def create_uploaded(self, upload_data: dict) -> Document:

        document = Document(
            title = upload_data["filename"],
            filename = upload_data["filename"],
            file_id = str(uuid4()),     #同文件上传为不同上传记录
            media_type = upload_data["media_type"],
            file_size = upload_data["file_size"],
            content_hash = upload_data["content_hash"],
            parse_status = "parsed",
            text_length = upload_data["text_length"],
            extracted_text = upload_data["text"]
        )

        try:
            self.db.add(document)

            # INSERT Document and obtain its primary key.
            self.db.flush()

            page_records = [
                DocumentPage(
                    document_id=document.id,
                    page_number=page["page_number"],
                    content=page["content"],
                    start_char=page["start_char"],
                    end_char=page["end_char"],
                )
                for page in upload_data.get("pages", [])
            ]

            self.db.add_all(page_records)

            # Document and DocumentPage share one transaction.
            self.db.commit()
            self.db.refresh(document)

        except Exception:
            self.db.rollback()
            raise
        
        return document