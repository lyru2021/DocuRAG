"""数据库连接和 ORM 元数据一致性测试。"""

from types import NoneType
from typing import get_args

from sqlalchemy import text

from app.models.document import Document


def test_document_file_size_annotation_matches_integer_column():
    column = Document.__table__.columns["file_size"]
    mapped_type = get_args(Document.__annotations__["file_size"])[0]

    assert column.type.python_type is int
    assert set(get_args(mapped_type)) == {int, NoneType}


def test_database_connection(db_session):
    result = db_session.execute(
        text("SELECT current_database()")
    ).scalar_one()

    assert result == "docurag_test"
