from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    PATIENT = "patient"
    COORDINATOR = "coordinator"
    ADMIN = "admin"


class CaseStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    PROVIDER_MATCHED = "provider_matched"
    QUOTED = "quoted"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentType(StrEnum):
    LAB_REPORT = "lab_report"
    IMAGING = "imaging"
    DISCHARGE_SUMMARY = "discharge_summary"
    INSURANCE = "insurance"
    OTHER = "other"


class CaseEventType(StrEnum):
    CASE_CREATED = "case_created"
    STATUS_CHANGED = "status_changed"
    COORDINATOR_ASSIGNED = "coordinator_assigned"
    PROVIDER_SHORTLISTED = "provider_shortlisted"
    PROVIDER_REMOVED = "provider_removed"
    QUOTE_RECORDED = "quote_recorded"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_PROCESSED = "document_processed"
    DOCUMENT_FAILED = "document_failed"
    DOCUMENT_DELETED = "document_deleted"
