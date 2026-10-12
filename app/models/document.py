from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(36), unique = True, nullable = True)
    media_type: Mapped[str | None] = mapped_column(String(100), nullable = True)
    file_size: Mapped[str | None] = mapped_column(Integer, nullable = True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable = True)
    parse_status: Mapped[str] = mapped_column(String(30),server_default="metadata_only",nullable=False,)
    text_length: Mapped[int | None] = mapped_column(Integer,nullable=True,)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan", passive_deletes=True)
    
class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False,index=True)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document: Mapped["Document"] = relationship(back_populates="chunks")