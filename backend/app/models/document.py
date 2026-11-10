from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentStatus, DocumentType

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.user import User

document_status_enum = SAEnum(
    DocumentStatus,
    name="document_status",
    values_callable=lambda enum: [member.value for member in enum],
)

document_type_enum = SAEnum(
    DocumentType,
    name="document_type",
    values_callable=lambda enum: [member.value for member in enum],
)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        document_status_enum,
        nullable=False,
        default=DocumentStatus.PENDING,
        server_default="pending",
    )
    doc_type: Mapped[DocumentType] = mapped_column(
        document_type_enum, nullable=False, default=DocumentType.OTHER, server_default="other"
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    case: Mapped[Case] = relationship(back_populates="documents")
    uploader: Mapped[User | None] = relationship()

    __table_args__ = (
        UniqueConstraint("s3_key", name="uq_documents_s3_key"),
        CheckConstraint("size_bytes >= 0", name="ck_documents_size_non_negative"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document {self.filename} ({self.status})>"
