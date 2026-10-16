"""论文元数据和章节结构的 ORM 模型。"""

from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaperMetadata(Base):
    """论文元数据模型。

    与 `documents` 一对一关联，保存标题、作者、年份、DOI 等可验证信息。
    """

    __tablename__ = "paper_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    paper_title: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    authors: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    publication_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    doi: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    metadata_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="unverified",
    )

    metadata_source: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )


class PaperSection(Base):
    """论文结构章节模型。

    当前章节由规则检测产生，`verification_status` 用于区分候选、人工确认或拒绝状态。
    """

    __tablename__ = "paper_sections"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "start_char",
            name="uq_paper_section_document_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    heading: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    start_char: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    detection_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    verification_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="candidate",
    )
