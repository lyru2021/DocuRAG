
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import (
    Chunk,
    Document,
    DocumentPage,
)
from app.services.page_mapper import find_chunk_page_range
from app.services.text_chunker import split_text


class ChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def replace_document_chunks(
        self,
        document_id: int,
        chunk_size: int = 300,
        overlap: int = 50,
    ) -> list[Chunk]:
        """
        Replace document chunks in one transaction.

        Also map chunk character offsets to PDF pages.
        """

        try:
            # 1. Load the document.
            document = self.db.get(Document, document_id)

            if document is None:
                raise ValueError("Document not found")

            if not document.extracted_text:
                raise ValueError(
                    "Document has no extracted text"
                )

            # 2. Split extracted text into chunks.
            parts = split_text(
                document.extracted_text,
                chunk_size=chunk_size,
                overlap=overlap,
            )

            if not parts:
                raise ValueError("No chunks generated")

            # 3. Load PDF page mappings.
            # TXT documents normally have no page records.
            pages = list(
                self.db.scalars(
                    select(DocumentPage)
                    .where(
                        DocumentPage.document_id == document_id
                    )
                    .order_by(DocumentPage.page_number)
                ).all()
            )

            # 4. Remove previous chunks.
            self.db.execute(
                delete(Chunk).where(
                    Chunk.document_id == document_id
                )
            )

            # 5. Build new chunks with page ranges.
            chunks = []

            for part in parts:
                page_start, page_end = find_chunk_page_range(
                    part.start_char,
                    part.end_char,
                    pages,
                )

                chunk = Chunk(
                    document_id=document_id,
                    chunk_index=part.chunk_index,
                    content=part.content,
                    start_char=part.start_char,
                    end_char=part.end_char,
                    page_start=page_start,
                    page_end=page_end,
                )

                chunks.append(chunk)

            # 6. Save all chunks.
            self.db.add_all(chunks)
            self.db.commit()

            return chunks

        except Exception:
            self.db.rollback()
            raise

    def list_document_chunks(
        self,
        document_id: int,
    ) -> list[Chunk]:
        statement = (
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.chunk_index)
        )

        return list(
            self.db.scalars(statement).all()
        )
