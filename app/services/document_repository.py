"""文档仓储服务。

封装 `Document` 与 `DocumentPage` 的数据库读写和事务回滚边界。
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage
from app.schemas.document import DocumentCreate


class DocumentRepository:
    """文档表的数据库访问入口。

    仓储层集中处理 `Document` 和相关页面记录的持久化，并在写操作失败时回滚事务。
    """

    def __init__(self, db: Session):
        self.db = db

    def create(self, data: DocumentCreate) -> Document:
        """创建仅包含元数据的文档记录。

        Args:
            data: 已通过 Pydantic 校验的文档创建请求。

        Returns:
            Document: 已提交并刷新后的 ORM 对象。

        Raises:
            Exception: 数据库提交失败时回滚当前 Session 后继续抛出原异常。
        """

        document = Document(
            title=data.title,
            filename=data.filename,
        )

        try:
            self.db.add(document)
            self.db.commit()
            self.db.refresh(document)
        except Exception:
            # 写操作失败后必须回滚，否则同一个 Session 会停留在失败事务状态。
            self.db.rollback()
            raise

        return document

    def list_all(self) -> list[Document]:
        """按主键升序返回所有文档。"""

        statement = select(Document).order_by(Document.id)

        return list(
            self.db.scalars(statement).all()
        )

    def get(self, document_id: int) -> Document | None:
        """按主键读取文档。

        Args:
            document_id: `documents.id` 主键。

        Returns:
            Document | None: 找到时返回 ORM 对象，否则返回 None。
        """

        return self.db.get(Document, document_id)

    def delete(self, document_id: int) -> bool:
        """删除指定文档。

        Args:
            document_id: `documents.id` 主键。

        Returns:
            bool: 删除成功返回 True；文档不存在返回 False。

        Raises:
            Exception: 数据库提交失败时回滚当前 Session 后继续抛出原异常。
        """

        document = self.get(document_id)

        if document is None:
            return False

        try:
            self.db.delete(document)
            self.db.commit()
        except Exception:
            # 删除依赖数据库级联和 ORM 级联；失败时回滚以恢复 Session 可用性。
            self.db.rollback()
            raise

        return True

    def create_uploaded(self, upload_data: dict) -> Document:
        """创建上传文档及其页面映射记录。

        Args:
            upload_data: 上传服务生成的数据字典，至少包含 filename、media_type、
                file_size、content_hash、text_length、text，以及可选 pages/file_id。

        Returns:
            Document: 已提交并刷新后的文档对象。

        Raises:
            KeyError: `upload_data` 缺少必需字段。
            Exception: 数据库写入失败时回滚当前 Session 后继续抛出原异常。
        """

        document = Document(
            title=upload_data["filename"],
            filename=upload_data["filename"],
            # 如果没有提供 file_id，仍使用原来的 UUID 生成逻辑。
            file_id=upload_data.get("file_id") or str(uuid4()),
            media_type=upload_data["media_type"],
            file_size=upload_data["file_size"],
            content_hash=upload_data["content_hash"],
            parse_status="parsed",
            text_length=upload_data["text_length"],
            extracted_text=upload_data["text"],
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
            # Document 和 DocumentPage 必须同生共死，避免留下无法映射页码的半成品记录。
            self.db.rollback()
            raise

        return document
