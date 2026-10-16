"""
解析论文 PDF，并在当前数据库事务中保存页面和 Chunk。
"""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage
from app.services.chunk_repository import ChunkRepository
from app.services.document_parser import parse_pdf_with_pages


class PaperProcessingService:
    """封装 PDF 解析和索引数据写入，不负责提交事务。"""

    def __init__(self, db: Session):
        self.db = db

    def process_pdf(
        self,
        document_id: int,
        pdf_bytes: bytes,
        chunk_size: int = 300,
        overlap: int = 50,
    ) -> int:
        """
        重新解析 PDF，保存逐页文本及 Chunk。

        返回生成的 Chunk 数量。

        注意：
        本方法不调用 commit，也不主动 rollback。
        事务由上层 Worker 统一管理。
        """

        document = self.db.get(Document, document_id)

        if document is None:
            raise ValueError("Document not found")

        # 先完成 PDF 解析，避免在解析失败时修改旧数据。
        parsed = parse_pdf_with_pages(pdf_bytes)

        if not parsed.text.strip():
            raise ValueError("PDF has no extractable text")

        # 删除旧页面，避免重新处理时产生重复记录。
        self.db.execute(
            delete(DocumentPage).where(
                DocumentPage.document_id == document_id
            )
        )

        pages = [
            DocumentPage(
                document_id=document_id,
                page_number=page.page_number,
                content=page.text,
                start_char=page.start_char,
                end_char=page.end_char,
            )
            for page in parsed.pages
        ]

        self.db.add_all(pages)

        # 更新全文。Chunk 的字符偏移必须基于同一份文本。
        document.extracted_text = parsed.text
        document.text_length = len(parsed.text)
        
        # 解析结果和任务 completed 状态由 Worker 在同一事务中提交。
        document.parse_status = "parsed"

        self.db.flush()

        # 不提交事务：页面、正文和 Chunk 必须一起成功或回滚。
        chunks = ChunkRepository(
            self.db
        ).replace_document_chunks(
            document_id=document_id,
            chunk_size=chunk_size,
            overlap=overlap,
            auto_commit=False,
        )

        return len(chunks)
