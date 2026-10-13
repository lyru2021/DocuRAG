from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Chunk, Document, DocumentPage
from app.models.paper import PaperMetadata
from app.services.evidence_validator import validate_evidence

class PaperQueryService:
    def __init__(self, db: Session):
        self.db = db

    def get_document(self, document_id: int):
        return self.db.get(Document, document_id)

    def get_metadata(self, document_id: int):
        return self.db.scalar(
            select(PaperMetadata).where(
                PaperMetadata.document_id == document_id
            )
        )

    def get_pages(self, document_id: int):
        return list(
            self.db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            ).all()
        )

    def get_chunks(self, document_id: int):
        return list(
            self.db.scalars(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.chunk_index)
            ).all()
        )

    
    def get_evidence(
        self,
        document_id: int,
        chunk_id: int,
    ):
        document = self.get_document(document_id)

        if document is None:
            return None

        chunk = self.db.get(Chunk, chunk_id)

        if chunk is None or chunk.document_id != document_id:
            return None

        pages = self.get_pages(document_id)

        validation = validate_evidence(
            full_text=document.extracted_text or "",
            chunk=chunk,
            pages=pages,
        )

        return {
            "document_id": document.id,
            "chunk_id": chunk.id,
            "filename": document.filename,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "start_char": chunk.start_char,
            "end_char": chunk.end_char,
            "quote": chunk.content,
            "verified": validation.verified,
            "text_verified": validation.text_verified,
            "pages_verified": validation.pages_verified,
        }
