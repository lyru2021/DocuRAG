"""手动检查文档 chunk 与 PDF 页码映射的实验脚本。"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document import Chunk, Document
from app.services.chunk_repository import ChunkRepository

# 手动实验脚本：运行前把这里改成真实上传后的文档 ID。
DOCUMENT_ID = 30


def main():
    """重新生成指定文档的 chunk，并打印前几个 chunk 的页码映射。"""

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
