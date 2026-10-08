from datetime import datetime,timezone
from app.schemas.document import DocumentCreate, DocumentRead

class DocumentStore:
    def __init__(self):
        self._documents: dict[int, DocumentRead] = {}
        self._next_id = 1

    def create(self, data: DocumentCreate) -> DocumentRead:
        document = DocumentRead(
            id=self._next_id,
            title=data.title,
            filename=data.filename,
            created_at=datetime.now(timezone.utc)
        )

        self._documents[document.id] = document
        self._next_id += 1
        return document

    def list_all(self) -> list[DocumentRead]:
        return list(self._documents.values())
    
    def get(self, document_id: int) -> DocumentRead | None:
        return self._documents.get(document_id)
    
    def delete(self, document_id: int) -> bool:
        if document_id not in self._documents:
            return False
        del self._documents[document_id]
        return True
    
store = DocumentStore()

def get_document_store() -> DocumentStore:
    return store