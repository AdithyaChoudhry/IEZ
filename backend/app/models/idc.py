"""
IDC (Inter Discipline Check) SQLAlchemy models.
Completely independent — touches no existing tables.
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from ..auth.models import Base


class IDCSession(Base):
    __tablename__ = "idc_sessions"
    id              = Column(Integer, primary_key=True, index=True)
    idc_number      = Column(String, unique=True, index=True, nullable=False)
    project_name    = Column(String, nullable=False)
    document_number = Column(String, nullable=False)
    document_title  = Column(String, nullable=False)
    revision_number = Column(String, nullable=False)
    document_category = Column(String, nullable=False)
    due_date        = Column(String, nullable=False)
    remarks         = Column(Text, nullable=True)
    status          = Column(String, default="active")   # active | frozen
    created_by_emp  = Column(String, nullable=False)     # employee_id
    created_by_name = Column(String, nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    frozen_at       = Column(DateTime, nullable=True)
    frozen_by_emp   = Column(String, nullable=True)
    frozen_by_name  = Column(String, nullable=True)

    documents   = relationship("IDCDocument",   back_populates="session", cascade="all,delete-orphan")
    disciplines = relationship("IDCDiscipline", back_populates="session", cascade="all,delete-orphan")
    annotations = relationship("IDCAnnotation", back_populates="session", cascade="all,delete-orphan")
    comments    = relationship("IDCComment",    back_populates="session", cascade="all,delete-orphan")
    approvals   = relationship("IDCApproval",   back_populates="session", cascade="all,delete-orphan")


class IDCDocument(Base):
    __tablename__ = "idc_documents"
    id                = Column(Integer, primary_key=True, index=True)
    session_id        = Column(Integer, ForeignKey("idc_sessions.id"), nullable=False)
    filename          = Column(String, nullable=False)    # stored filename on disk
    original_filename = Column(String, nullable=False)
    file_type         = Column(String, nullable=False)    # pdf | dwg | dxf | zip
    file_size         = Column(Integer, default=0)
    uploaded_by_emp   = Column(String, nullable=False)
    uploaded_by_name  = Column(String, nullable=False)
    uploaded_at       = Column(DateTime, default=datetime.utcnow)
    session = relationship("IDCSession", back_populates="documents")


class IDCDiscipline(Base):
    __tablename__ = "idc_disciplines"
    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("idc_sessions.id"), nullable=False)
    discipline = Column(String, nullable=False)
    session    = relationship("IDCSession", back_populates="disciplines")


class IDCAnnotation(Base):
    __tablename__ = "idc_annotations"
    id            = Column(Integer, primary_key=True, index=True)
    session_id    = Column(Integer, ForeignKey("idc_sessions.id"), nullable=False)
    document_id   = Column(Integer, ForeignKey("idc_documents.id"), nullable=False)
    ann_uuid      = Column(String, unique=True, index=True, nullable=False)  # client UUID
    tool_type     = Column(String, nullable=False)  # arrow|rect|circle|text|cloud|highlight|freehand|line
    page_number   = Column(Integer, default=1)
    x             = Column(Float, default=0)
    y             = Column(Float, default=0)
    width         = Column(Float, nullable=True)
    height        = Column(Float, nullable=True)
    data_json     = Column(Text, default="{}")      # tool-specific JSON (points, text, etc.)
    color         = Column(String, default="#000000")
    author_emp    = Column(String, nullable=False)
    author_name   = Column(String, nullable=False)
    discipline    = Column(String, nullable=False)
    is_deleted    = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, nullable=True)
    session       = relationship("IDCSession", back_populates="annotations")


class IDCComment(Base):
    __tablename__ = "idc_comments"
    id             = Column(Integer, primary_key=True, index=True)
    session_id     = Column(Integer, ForeignKey("idc_sessions.id"), nullable=False)
    ann_uuid       = Column(String, nullable=True)   # links to IDCAnnotation.ann_uuid
    comment_number = Column(String, nullable=False)  # IDC-001, IDC-002 …
    page_number    = Column(Integer, default=1)
    author_emp     = Column(String, nullable=False)
    author_name    = Column(String, nullable=False)
    discipline     = Column(String, nullable=False)
    comment_text   = Column(Text, nullable=False)
    priority       = Column(String, default="Normal")   # Critical|High|Normal|Low
    status         = Column(String, default="Open")     # Open|Under Review|Resolved|Rejected|Need Clarification|Closed
    category       = Column(String, default="General")  # General|Design|Safety|Constructability|Vendor|Drawing Correction|Documentation|LLR Related|SOP Related|IDC Observation
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, nullable=True)
    resolved_by    = Column(String, nullable=True)
    resolved_at    = Column(DateTime, nullable=True)
    session = relationship("IDCSession", back_populates="comments")
    replies = relationship("IDCCommentReply", back_populates="comment", cascade="all,delete-orphan")


class IDCCommentReply(Base):
    __tablename__ = "idc_comment_replies"
    id          = Column(Integer, primary_key=True, index=True)
    comment_id  = Column(Integer, ForeignKey("idc_comments.id"), nullable=False)
    author_emp  = Column(String, nullable=False)
    author_name = Column(String, nullable=False)
    discipline  = Column(String, nullable=False)
    reply_text  = Column(Text, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    comment = relationship("IDCComment", back_populates="replies")


class IDCApproval(Base):
    __tablename__ = "idc_approvals"
    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(Integer, ForeignKey("idc_sessions.id"), nullable=False)
    discipline   = Column(String, nullable=False)
    employee_id  = Column(String, nullable=False)
    employee_name= Column(String, nullable=False)
    approved_at  = Column(DateTime, default=datetime.utcnow)
    session = relationship("IDCSession", back_populates="approvals")
