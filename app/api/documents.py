from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentCreate, DocumentRead
from app.services.document_repository import DocumentRepository

router = APIRouter(prefix="/documents",#给当前路由模块中的接口统一增加/documents前缀
                   tags=["Documents"])#使这些接口在Swagger UI中归类为Documents

DbDep = Annotated[Session, Depends(get_db)]
#定义一个依赖注入类型别名 DbDep，表示一个 SQLAlchemy 的 Session 对象，通过 get_db() 函数获取。

@router.post(
    "", 
    response_model=DocumentRead, 
    status_code=status.HTTP_201_CREATED
    )
def create_document(
    data: DocumentCreate, 
    db: DbDep
    ):
    repository = DocumentRepository(db)
    return repository.create(data)

@router.get(
    "",
    response_model=list[DocumentRead]
)
def list_documents(db: DbDep):
    repository = DocumentRepository(db)
    return repository.list_all()

@router.get(
    "/{document_id}",
    response_model=DocumentRead
)
def get_document(
    document_id: int,
    db: DbDep
):
    repository = DocumentRepository(db)
    document = repository.get(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document not found"
        )
    return document

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_document(
    document_id: int,
    db: DbDep
):
    repository = DocumentRepository(db)
    deleted = repository.delete(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )