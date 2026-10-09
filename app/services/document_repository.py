from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
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
