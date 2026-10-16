"""验证论文元数据组合检索与稳定排序。"""

from app.models.document import Document
from app.services.paper_search_repository import PaperSearchRepository


def test_search_papers_by_metadata(db_session):
    """标题、作者和年份可以组合过滤。"""

    paper = Document(
        title="Graph Neural Networks for Fraud Detection",
        filename="graph-paper.pdf",
        authors="Alice Zhang, Bob Chen",
        publication_year=2025,
    )

    db_session.add(paper)
    db_session.commit()

    repo = PaperSearchRepository(db_session)

    results = repo.search(
        title="graph neural",
        author="alice",
        year=2025,
    )

    assert [item.id for item in results] == [paper.id]


def test_search_papers_by_document_id(db_session):
    """可以通过真实数据库 ID 精确定位论文。"""

    paper = Document(
        title="High Temperature Superconducting Magnets",
        filename="hts-paper.pdf",
        publication_year=2024,
    )

    db_session.add(paper)
    db_session.commit()

    repo = PaperSearchRepository(db_session)

    results = repo.search(document_id=paper.id)

    assert len(results) == 1
    assert results[0].id == paper.id


def test_search_papers_escapes_like_wildcards(db_session):
    """百分号不能被当作任意长度通配符。"""

    matching = Document(
        title="Accuracy 95% in Experiments",
        filename="accuracy.pdf",
    )

    nonmatching = Document(
        title="Accuracy 950 in Experiments",
        filename="accuracy-other.pdf",
    )

    db_session.add_all([matching, nonmatching])
    db_session.commit()

    repo = PaperSearchRepository(db_session)

    results = repo.search(title="95%")

    assert [item.id for item in results] == [matching.id]


def test_search_papers_stable_order(db_session):
    """相同条件下按文档主键升序返回。"""

    papers = [
        Document(title=f"Paper {i}", filename=f"paper-{i}.pdf")
        for i in range(3)
    ]

    db_session.add_all(papers)
    db_session.commit()

    repo = PaperSearchRepository(db_session)

    first = [paper.id for paper in repo.search(title="Paper")]
    second = [paper.id for paper in repo.search(title="Paper")]

    assert first == second
    assert first == sorted(first)