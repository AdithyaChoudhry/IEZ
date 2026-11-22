"""
Deliverable cover sheet records - the Cover Sheet Generator's per-document data that the Instrument List, I/O List,
Cable Schedule, Loop Wiring and Datasheet generators reuse.

One record per (project, document type, sub key); the sub key separates datasheets of different instrument types
("" for the other documents). The MDL stays the authority for document number and title: only the MDL record id is
kept here and the number / title are read from the active MDL every time. Only adds a new table.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint

from ..auth.models import Base


class DeliverableCover(Base):
    __tablename__ = "deliverable_covers"
    __table_args__ = (UniqueConstraint("project_id", "doc_type", "sub_key", name="uq_deliverable_cover"),)

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, index=True, nullable=False)
    doc_type = Column(String, nullable=False)              # instrument_list | io_list | cable_schedule | loop_wiring | datasheet
    sub_key = Column(String, nullable=False, default="")   # datasheet: library template id; others ""
    mdl_record_id = Column(String, nullable=True)          # chosen by the engineer (None = use the keyword match)
    project_info_json = Column(Text, nullable=True)        # client, PMC, contractor, project description, unit no, class ...
    revisions_json = Column(Text, nullable=True)           # [{rev_no, date, description, prepared_by, checked_by, approved_by}]
    approval_request_id = Column(Integer, nullable=True)   # approval_requests.id (request_type "coversheet")
    approval_fingerprint = Column(String, nullable=True)   # the content that was sent for approval
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
