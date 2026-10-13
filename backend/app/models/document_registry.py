"""
Document registry SQLAlchemy models.

Project-level register of every controlled deliverable the generators produce
(Instrument List, I/O List, Cable Schedule, Loop Wiring) plus the source-file
revisions they were generated from and the Coversheet links to them.

Only adds new tables - touches no existing ones.
"""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from ..auth.models import Base


class Project(Base):
    __tablename__ = "projects"
    id         = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, unique=True, index=True, nullable=False)  # e.g. "10P211"
    name       = Column(String, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SourceVersion(Base):
    """One uploaded source file revision (IODB, or the Loop Wiring input) per project."""
    __tablename__ = "document_source_versions"
    __table_args__ = (UniqueConstraint("project_id", "kind", "sha256", name="uq_source_version"),)

    id         = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, index=True, nullable=False)
    kind       = Column(String, nullable=False)          # "iodb" | "loop_input"
    rev_no     = Column(Integer, nullable=False)         # 1, 2, 3 ... per (project, kind)
    sha256     = Column(String, nullable=False)
    filename   = Column(String, nullable=False)
    file_path  = Column(String, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GeneratedDocument(Base):
    """One generated revision of a deliverable. Revisions are append-only."""
    __tablename__ = "generated_documents"

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(String, index=True, nullable=False)
    module          = Column(String, index=True, nullable=False)   # instrument_list | io_list | cable_schedule | loop_wiring
    document_name   = Column(String, nullable=False)
    document_number = Column(String, nullable=False)
    revision        = Column(Integer, nullable=False)               # 1, 2, 3 ... per (project, module)
    status          = Column(String, nullable=False, default="GENERATED")
    generation_status = Column(String, nullable=False, default="success")  # success | failed
    error_message   = Column(Text, nullable=True)

    generated_at    = Column(DateTime, default=datetime.utcnow)
    generated_by    = Column(String, nullable=True)

    source_version_id = Column(Integer, ForeignKey("document_source_versions.id"), nullable=True)
    source_kind     = Column(String, nullable=True)
    source_rev_no   = Column(Integer, nullable=True)
    source_sha256   = Column(String, nullable=True)

    filename        = Column(String, nullable=True)
    output_file_path = Column(String, nullable=True)
    template_path   = Column(String, nullable=True)       # stored template, needed to regenerate
    record_count    = Column(Integer, nullable=True)
    sheet_count     = Column(Integer, nullable=True)
    params_json     = Column(Text, nullable=True)         # generator parameters, needed to regenerate

    superseded_by      = Column(Integer, nullable=True)   # id of the newer revision
    parent_document_id = Column(Integer, nullable=True)   # id of the previous revision


class CoversheetLink(Base):
    """Which revision of a module is currently linked to the project's Coversheet."""
    __tablename__ = "coversheet_links"
    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(String, index=True, nullable=False)
    module      = Column(String, nullable=False)
    document_id = Column(Integer, ForeignKey("generated_documents.id"), nullable=False)
    active      = Column(Boolean, default=True, nullable=False)
    linked_by   = Column(String, nullable=True)
    linked_at   = Column(DateTime, default=datetime.utcnow)
    unlinked_by = Column(String, nullable=True)
    unlinked_at = Column(DateTime, nullable=True)


class DocumentAuditLog(Base):
    __tablename__ = "document_audit_log"
    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(String, index=True, nullable=False)
    module      = Column(String, nullable=True)
    document_id = Column(Integer, nullable=True)
    action      = Column(String, nullable=False)   # generated | generation_failed | regenerated | connected | disconnected | source_uploaded | status_changed
    actor       = Column(String, nullable=True)
    at          = Column(DateTime, default=datetime.utcnow)
    details     = Column(Text, nullable=True)      # JSON
