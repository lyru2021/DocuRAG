"""文档元数据 API。

提供 `/documents` 下的基础 CRUD 路由，持久化细节委托给 `DocumentRepository`。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentCreate, DocumentRead
from app.services.document_repository import DocumentRepository
from app.services.document_deletion_service import DocumentDeletionService

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

DbDep = Annotated[Session, Depends(get_db)]


# 路由函数保持薄层，只负责 HTTP 状态和错误语义；数据库操作交给仓储层。
@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    data: DocumentCreate,
    db: DbDep,
):
    repository = DocumentRepository(db)
    return repository.create(data)


@router.get(
    "",
    response_model=list[DocumentRead],
)
def list_documents(db: DbDep):
    repository = DocumentRepository(db)
    return repository.list_all()


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
)
def get_document(
    document_id: int,
    db: DbDep,
):
    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: int,
    db: DbDep,
):
    """删除无活跃处理任务的文档及其本地原始文件。"""

    result = DocumentDeletionService(db).delete(document_id)

    if result == "not_found":
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if result == "active_job":
        raise HTTPException(
            status_code=409,
            detail="Document has an active processing job",
        )