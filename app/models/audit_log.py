"""Audit log model for tracking all system actions"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from datetime import datetime

Base = declarative_base()

class ActionType(enum.Enum):
    """Types of actions that can be logged"""
    MONITORING_CHECK = "monitoring_check"
    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_RESOLVED = "incident_resolved"
    COMMAND_EXECUTED = "command_executed"
    AUTO_FIX_ATTEMPTED = "auto_fix_attempted"
    AUTO_FIX_SUCCESSFUL = "auto_fix_successful"
    AUTO_FIX_FAILED = "auto_fix_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    SOP_CONSULTED = "sop_consulted"
    LLM_QUERY = "llm_query"
    EMAIL_SENT = "email_sent"
    WEBHOOK_RECEIVED = "webhook_received"
    CONFIGURATION_CHANGED = "configuration_changed"
    ESCALATION = "escalation"

class AuditLog(Base):
    """Audit log for tracking all system actions"""
    
    __tablename__ = 'audit_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    action_type = Column(Enum(ActionType), nullable=False)
    
    # Related entities
    incident_id = Column(Integer, ForeignKey('incidents.id'), nullable=True)
    user_id = Column(String(100))  # System user or operator
    
    # Action details
    action_description = Column(Text, nullable=False)
    command_executed = Column(Text)  # Command that was run
    command_output = Column(Text)   # Output from the command
    command_exit_code = Column(Integer)
    
    # Context information
    source_system = Column(String(100))  # kubernetes, aws, gcp, azure
    namespace = Column(String(100))
    affected_service = Column(String(200))
    
    # Request/Response data
    request_data = Column(Text)     # Input parameters/payload
    response_data = Column(Text)    # Response/result data
    
    # Success/failure tracking
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # LLM interaction details
    llm_model_used = Column(String(100))
    llm_prompt = Column(Text)
    llm_response = Column(Text)
    llm_tokens_used = Column(Integer)
    
    # Timing information
    duration_ms = Column(Integer)   # How long the action took
    
    # Metadata
    ip_address = Column(String(45))  # IPv4 or IPv6
    user_agent = Column(String(500))
    session_id = Column(String(100))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<AuditLog(id={self.id}, action_type='{self.action_type.value}', success={self.success})>"
    
    def to_dict(self):
        """Convert audit log to dictionary"""
        return {
            'id': self.id,
            'action_type': self.action_type.value if self.action_type else None,
            'incident_id': self.incident_id,
            'user_id': self.user_id,
            'action_description': self.action_description,
            'command_executed': self.command_executed,
            'command_output': self.command_output,
            'command_exit_code': self.command_exit_code,
            'source_system': self.source_system,
            'namespace': self.namespace,
            'affected_service': self.affected_service,
            'request_data': self.request_data,
            'response_data': self.response_data,
            'success': self.success,
            'error_message': self.error_message,
            'llm_model_used': self.llm_model_used,
            'llm_prompt': self.llm_prompt,
            'llm_response': self.llm_response,
            'llm_tokens_used': self.llm_tokens_used,
            'duration_ms': self.duration_ms,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }