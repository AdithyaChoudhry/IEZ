"""
Master Document List (MDL) SQLAlchemy models.

One *active* MDL per project; earlier uploads are kept (inactive) so the previous
revision can be reported and the audit trail stays intact. Only adds new tables.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from ..auth.models import Base


class ProjectMDL(Base):
    __tablename__ = "project_mdls"
    id             = Column(Integer, primary_key=True, index=True)
    project_id     = Column(String, index=True, nullable=False)
    filename       = Column(String, nullable=False)
    sheet_name     = Column(String, nullable=False)
    header_row     = Column(Integer, nullable=False)
    revision       = Column(String, nullable=True)           # "R4" or NULL (= not identified)
    revision_source = Column(String, nullable=True)          # "cover sheet" | "file name"
    document_count = Column(Integer, nullable=False)
    section_rows_ignored = Column(Integer, nullable=False, default=0)
    duplicate_doc_numbers = Column(Integer, nullable=False, default=0)
    warnings_json  = Column(Text, nullable=True)
    sha256         = Column(String, nullable=False)
    uploaded_by    = Column(String, nullable=True)
    uploaded_at    = Column(DateTime, default=datetime.utcnow)
    active         = Column(Boolean, nullable=False, default=True)
    replaced_at    = Column(DateTime, nullable=True)


class MDLRecord(Base):
    __tablename__ = "mdl_records"
    __table_args__ = (UniqueConstraint("mdl_id", "record_id", name="uq_mdl_record"),)

    id          = Column(Integer, primary_key=True, index=True)
    mdl_id      = Column(Integer, ForeignKey("project_mdls.id"), index=True, nullable=False)
    record_id   = Column(String, index=True, nullable=False)   # stable: DOC NO + DESCRIPTION
    ordinal     = Column(Integer, nullable=False)              # order in the MDL (not an identity)
    s_no        = Column(String, nullable=True)
    discipline  = Column(String, nullable=True)
    doc_no      = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    category    = Column(String, nullable=True)
    remarks     = Column(String, nullable=True)
