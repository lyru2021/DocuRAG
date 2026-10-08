from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.document import DocumentCreate, DocumentRead
from app.services.document_store import DocumentStore, get_document_store

router = APIRouter(prefix="/documents",#给当前路由模块中的接口统一增加/documents前缀
                   tags=["Documents"])#使这些接口在Swagger UI中归类为Documents

StoreDep = Annotated[DocumentStore, Depends(get_document_store)]
#当路由函数需要 store 时，让 FastAPI 通过 get_document_store() 获取仓储对象。

@router.post(
    "", 
    response_model=DocumentRead, 
    status_code=status.HTTP_201_CREATED
    )
def create_document(
    data: DocumentCreate, 
    store: StoreDep
    ):
    return store.create(data)

@router.get(
    "",
    response_model=list[DocumentRead]
)
def list_documents(store: StoreDep):
    return store.list_all()

@router.get(
    "/{document_id}",
    response_model=DocumentRead
)
def get_document(
    document_id: int,
    store: StoreDep
):
    document = store.get(document_id)
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
    store: StoreDep
):
    deleted = store.delete(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )