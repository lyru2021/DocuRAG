from unittest.mock import Mock

import pytest

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.document import Chunk
from app.schemas.document import DocumentCreate
from app.services.document_repository import DocumentRepository

def test_rollback_after_duplicate_chunk(db_session,sample_document):
    document_id = sample_document.id

    first_chunk = Chunk(
        document_id=document_id,
        chunk_index=0,
        content="Original chunk"
    )
    
    db_session.add(first_chunk)
    db_session.flush()

    duplicate_chunk = Chunk(
        document_id=document_id,
        chunk_index=0,  # Duplicate index
        content="Duplicate chunk"
    )

    db_session.add(duplicate_chunk)

    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()

    count = db_session.scalar(
        select(func.count()).select_from(Chunk)
    )

    assert count is not None
    assert count >=0


def test_repository_rolls_back_on_commit_failure():
    mock_db = Mock()

    mock_db.commit.side_effect = SQLAlchemyError("Simulated database failure")

    repository = DocumentRepository(mock_db)

    data = DocumentCreate(title = "Rollback Test", filename = "rollback.pdf")

    with pytest.raises(SQLAlchemyError, match="Simulated database failure"):
        repository.create(data)

    mock_db.rollback.assert_called_once()

    mock_db.refresh.assert_not_called()