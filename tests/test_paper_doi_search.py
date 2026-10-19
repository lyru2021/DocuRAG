"""验证 DOI 检索的精确匹配和输入边界。"""

from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.services.paper_search_repository import (
    PaperSearchRepository,
)


def test_doi_query_uses_exact_equality():
    """DOI 应使用完整字符串等值比较，而不是模糊匹配。"""

    db = Mock()
    db.scalars.return_value.all.return_value = []

    repository = PaperSearchRepository(db)

    result = repository.search(
        doi="10.1234/example",
        limit=5,
    )

    assert result == []

    statement = db.scalars.call_args.args[0]

    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )

    sql = str(compiled)

    assert "paper_metadata" in sql
    assert "JOIN" in sql
    assert "lower(paper_metadata.doi)" in sql
    assert "10.1234/example" in sql
    assert "LIKE" not in sql.upper()


def test_doi_query_rejects_blank_input():
    """空 DOI 不能退化为无条件论文查询。"""

    db = Mock()
    repository = PaperSearchRepository(db)

    with pytest.raises(ValueError, match="doi"):
        repository.search(doi="   ")

    db.scalars.assert_not_called()


def test_doi_query_is_case_insensitive():
    """DOI 大小写差异不应影响精确匹配条件。"""

    db = Mock()
    db.scalars.return_value.all.return_value = []

    repository = PaperSearchRepository(db)

    repository.search(doi="10.1234/Example")

    statement = db.scalars.call_args.args[0]

    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )

    assert "10.1234/example" in str(compiled)