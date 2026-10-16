"""早期内存版文档仓储。

当前业务路径使用 PostgreSQL 仓储；该模块仅保留为历史实现和学习对照。
"""

from datetime import datetime, timezone

from app.schemas.document import DocumentCreate, DocumentRead


class DocumentStore:
    """早期内存版文档仓储。

    当前 API 已改为通过 `DocumentRepository` 写 PostgreSQL；该类未在业务路由中使用。
    保留它是为了对照早期实现或学习测试替身，不代表当前持久化方案。
    """

    def __init__(self):
        self._documents: dict[int, DocumentRead] = {}
        self._next_id = 1

    def create(self, data: DocumentCreate) -> DocumentRead:
        """在进程内存中创建一条文档记录。"""

        document = DocumentRead(
            id=self._next_id,
            title=data.title,
            filename=data.filename,
            created_at=datetime.now(timezone.utc),
        )

        self._documents[document.id] = document
        self._next_id += 1
        return document

    def list_all(self) -> list[DocumentRead]:
        """返回当前进程内保存的所有文档。"""

        return list(self._documents.values())

    def get(self, document_id: int) -> DocumentRead | None:
        """按内存中的文档 ID 查询记录。"""

        return self._documents.get(document_id)

    def delete(self, document_id: int) -> bool:
        """删除内存中的文档记录。"""

        if document_id not in self._documents:
            return False

        del self._documents[document_id]
        return True


store = DocumentStore()


def get_document_store() -> DocumentStore:
    """返回进程级内存仓储实例。"""

    return store
