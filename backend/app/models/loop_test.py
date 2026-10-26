"""Saved loop templates for Loop Wiring (Test). Adds one new table; touches nothing existing."""
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from ..auth.models import Base


class LoopTestTemplate(Base):
    __tablename__ = "loop_test_templates"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    loop_type   = Column(String, nullable=False)
    config_json = Column(Text, nullable=False)       # components, order, wires, terminals, shielding, signals, layout
    created_by  = Column(String, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
