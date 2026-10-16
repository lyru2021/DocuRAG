"""公共测试夹具自身的验证。"""

from sqlalchemy import select

from app.models.document import Document


def test_sample_document_exists(db_session, sample_document):
    assert sample_document.id is not None
    assert sample_document.title == "Sample Document"
    assert sample_document.filename == "sample.pdf"

    statement = select(Document).where(Document.id == sample_document.id)
    result = db_session.scalar(statement)

    assert result is not None
    assert result.id == sample_document.id
