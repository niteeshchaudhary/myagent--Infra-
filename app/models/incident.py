"""Incident model for tracking infrastructure issues"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum
from datetime import datetime
from typing import Optional

Base = declarative_base()

class IncidentStatus(enum.Enum):
    """Incident status enumeration"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    ESCALATED = "escalated"

class IncidentSeverity(enum.Enum):
    """Incident severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Incident(Base):
    """Incident model for tracking infrastructure issues"""
    
    __tablename__ = 'incidents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(Enum(IncidentSeverity), default=IncidentSeverity.MEDIUM)
    status = Column(Enum(IncidentStatus), default=IncidentStatus.OPEN)
    
    # Source information
    source = Column(String(50), nullable=False)  # polling or webhook
    source_system = Column(String(100))  # kubernetes, aws, gcp, azure
    affected_service = Column(String(200))
    namespace = Column(String(100))
    
    # Incident details
    error_message = Column(Text)
    stack_trace = Column(Text)
    logs_path = Column(String(500))  # Path to zipped logs
    webhook_payload = Column(Text)  # JSON payload from webhook
    
    # Resolution information
    is_known_issue = Column(Boolean, default=False)
    sop_document_id = Column(Integer)  # Reference to SOP document
    resolution_steps = Column(Text)
    resolution_notes = Column(Text)
    
    # Auto-fix information
    auto_fix_attempted = Column(Boolean, default=False)
    auto_fix_successful = Column(Boolean, default=False)
    auto_fix_commands = Column(Text)  # JSON array of commands executed
    
    # Approval workflow
    requires_approval = Column(Boolean, default=False)
    approval_requested = Column(Boolean, default=False)
    approval_granted = Column(Boolean, default=False)
    approver = Column(String(100))
    approval_notes = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True))
    escalated_at = Column(DateTime(timezone=True))
    
    # Assignment
    assigned_to = Column(String(100))
    escalation_contact = Column(String(200))
    
    def __repr__(self):
        return f"<Incident(id={self.id}, title='{self.title}', status='{self.status.value}', severity='{self.severity.value}')>"
    
    def to_dict(self):
        """Convert incident to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'severity': self.severity.value if self.severity else None,
            'status': self.status.value if self.status else None,
            'source': self.source,
            'source_system': self.source_system,
            'affected_service': self.affected_service,
            'namespace': self.namespace,
            'error_message': self.error_message,
            'stack_trace': self.stack_trace,
            'logs_path': self.logs_path,
            'is_known_issue': self.is_known_issue,
            'sop_document_id': self.sop_document_id,
            'resolution_steps': self.resolution_steps,
            'resolution_notes': self.resolution_notes,
            'auto_fix_attempted': self.auto_fix_attempted,
            'auto_fix_successful': self.auto_fix_successful,
            'auto_fix_commands': self.auto_fix_commands,
            'requires_approval': self.requires_approval,
            'approval_requested': self.approval_requested,
            'approval_granted': self.approval_granted,
            'approver': self.approver,
            'approval_notes': self.approval_notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'escalated_at': self.escalated_at.isoformat() if self.escalated_at else None,
            'assigned_to': self.assigned_to,
            'escalation_contact': self.escalation_contact
        }