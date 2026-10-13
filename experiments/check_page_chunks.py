from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Chunk, Document
from app.services.chunk_repository import ChunkRepository

DOCUMENT_ID = 30  # 改成刚才真实上传的 ID


def main():
    with SessionLocal() as db:
        document = db.get(Document, DOCUMENT_ID)

        if document is None:
            print("Document not found.")
            return

        repository = ChunkRepository(db)

        chunks = repository.replace_document_chunks(
            document_id=DOCUMENT_ID,
            chunk_size=300,
            overlap=50,
        )

        print("Document:", document.filename)
        print("Chunk count:", len(chunks))

        saved_chunks = db.scalars(
            select(Chunk)
            .where(Chunk.document_id == DOCUMENT_ID)
            .order_by(Chunk.chunk_index)
        ).all()

        for chunk in saved_chunks[:10]:
            print(
                f"Chunk {chunk.chunk_index}: "
                f"chars [{chunk.start_char}, {chunk.end_char}), "
                f"PDF pages {chunk.page_start}-{chunk.page_end}"
            )

            assert (
                document.extracted_text[
                    chunk.start_char:chunk.end_char
                ]
                == chunk.content
            )


if __name__ == "__main__":
    main()
