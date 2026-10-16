"""论文章节检测结果的持久化服务。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage
from app.models.paper import PaperSection
from app.services.section_detector import detect_sections


class PaperSectionRepository:
    """论文结构章节的检测与保存入口。"""

    def __init__(self, db: Session):
        self.db = db

    def detect_and_save(
        self,
        document_id: int,
    ) -> list[PaperSection]:
        """检测论文标题并保存为候选章节。

        Args:
            document_id: 已解析 PDF 文档的主键。

        Returns:
            list[PaperSection]: 当前文档下按 start_char 排序的全部章节。

        Raises:
            ValueError: 文档不存在、没有解析文本，或缺少 PDF 页码映射。
            Exception: 数据库提交失败时回滚当前 Session 后继续抛出原异常。
        """

        try:
            document = self.db.get(Document, document_id)

            if document is None:
                raise ValueError("Document not found")

            if not document.extracted_text:
                raise ValueError("Document has no extracted text")

            pages = list(
                self.db.scalars(
                    select(DocumentPage)
                    .where(
                        DocumentPage.document_id == document_id
                    )
                    .order_by(DocumentPage.page_number)
                ).all()
            )

            if not pages:
                raise ValueError(
                    "Document has no PDF page mappings"
                )

            candidates = detect_sections(
                document.extracted_text,
                pages,
            )

            existing_sections = list(
                self.db.scalars(
                    select(PaperSection).where(
                        PaperSection.document_id == document_id
                    )
                ).all()
            )

            existing_by_start = {
                section.start_char: section
                for section in existing_sections
            }

            for candidate in candidates:
                existing = existing_by_start.get(
                    candidate.start_char
                )

                if existing is not None:
                    # Never overwrite a manually confirmed
                    # or rejected section.
                    # 重新检测只补充新章节，不覆盖人工校验过的状态。
                    continue

                section = PaperSection(
                    document_id=document_id,
                    heading=candidate.heading,
                    page_number=candidate.page_number,
                    start_char=candidate.start_char,
                    detection_method=candidate.detection_method,
                    verification_status="candidate",
                )

                self.db.add(section)

            self.db.commit()

            return list(
                self.db.scalars(
                    select(PaperSection)
                    .where(PaperSection.document_id == document_id)
                    .order_by(PaperSection.start_char)
                ).all()
            )

        except Exception:
            # 章节检测会批量新增记录；失败时回滚，避免保存部分候选结果。
            self.db.rollback()
            raise
