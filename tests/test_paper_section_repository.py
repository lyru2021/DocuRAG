from sqlalchemy import select

from app.models.document import Document, DocumentPage
from app.models.paper import PaperSection
from app.services.paper_section_repository import (
    PaperSectionRepository,
)


def create_paper_with_pages(db_session):
    text = (
        "1 Introduction\n"
        "Background of this research.\n\n"
        "2 Methods\n"
        "Experimental details.\n\n"
        "3 Results\n"
        "The results are discussed."
    )

    document = Document(
        title="Paper Section Test",
        filename="paper.pdf",
        extracted_text=text,
        parse_status="parsed",
    )

    db_session.add(document)
    db_session.flush()

    page = DocumentPage(
        document_id=document.id,
        page_number=1,
        content=text,
        start_char=0,
        end_char=len(text),
    )

    db_session.add(page)
    db_session.flush()

    return document


def test_detect_and_save_sections(db_session):
    document = create_paper_with_pages(db_session)

    repo = PaperSectionRepository(db_session)
    sections = repo.detect_and_save(document.id)

    assert len(sections) == 3

    assert [s.heading for s in sections] == [
        "1 Introduction",
        "2 Methods",
        "3 Results",
    ]

    assert all(
        s.verification_status == "candidate"
        for s in sections
    )


def test_redetect_does_not_duplicate(db_session):
    document = create_paper_with_pages(db_session)

    repo = PaperSectionRepository(db_session)

    first = repo.detect_and_save(document.id)
    second = repo.detect_and_save(document.id)

    assert len(first) == 3
    assert len(second) == 3

    saved = list(
        db_session.scalars(
            select(PaperSection).where(
                PaperSection.document_id == document.id
            )
        ).all()
    )

    assert len(saved) == 3


def test_redetect_preserves_confirmed_status(db_session):
    document = create_paper_with_pages(db_session)

    repo = PaperSectionRepository(db_session)
    sections = repo.detect_and_save(document.id)

    sections[0].verification_status = "confirmed"
    db_session.commit()

    updated = repo.detect_and_save(document.id)

    assert updated[0].verification_status == "confirmed"


def test_missing_document_raises_error(db_session):
    repo = PaperSectionRepository(db_session)

    try:
        repo.detect_and_save(999999999)
    except ValueError as exc:
        assert str(exc) == "Document not found"
    else:
        raise AssertionError("Expected ValueError")


def test_section_offsets_match_original_text(db_session):
    document = create_paper_with_pages(db_session)

    repo = PaperSectionRepository(db_session)
    sections = repo.detect_and_save(document.id)

    for section in sections:
        assert document.extracted_text[
            section.start_char:
        ].startswith(section.heading)
