from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentPage
from app.models.paper import PaperSection
from app.services.section_detector import detect_sections


class PaperSectionRepository:
    def __init__(self, db: Session):
        self.db = db

    def detect_and_save(
        self,
        document_id: int,
    ) -> list[PaperSection]:
        try:
            document = self.db.get(Document, document_id)

            if document is None:
                raise ValueError("Document not found")

            if not document.extracted_text:
                raise ValueError("Document has no extracted text")

            pages = list(
                self.db.scalars(
                    select(DocumentPage)
                    .where(
                        DocumentPage.document_id == document_id
                    )
                    .order_by(DocumentPage.page_number)
                ).all()
            )

            if not pages:
                raise ValueError(
                    "Document has no PDF page mappings"
                )

            candidates = detect_sections(
                document.extracted_text,
                pages,
            )

            existing_sections = list(
                self.db.scalars(
                    select(PaperSection).where(
                        PaperSection.document_id == document_id
                    )
                ).all()
            )

            existing_by_start = {
                section.start_char: section
                for section in existing_sections
            }

            for candidate in candidates:
                existing = existing_by_start.get(
                    candidate.start_char
                )

                if existing is not None:
                    # Never overwrite a manually confirmed
                    # or rejected section.
                    continue

                section = PaperSection(
                    document_id=document_id,
                    heading=candidate.heading,
                    page_number=candidate.page_number,
                    start_char=candidate.start_char,
                    detection_method=candidate.detection_method,
                    verification_status="candidate",
                )

                self.db.add(section)

            self.db.commit()

            return list(
                self.db.scalars(
                    select(PaperSection)
                    .where(PaperSection.document_id == document_id)
                    .order_by(PaperSection.start_char)
                ).all()
            )

        except Exception:
            self.db.rollback()
            raise
