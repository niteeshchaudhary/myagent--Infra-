"""Approval request model and service"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum

from app.database.database import db_service
from app.models.incident import Incident
from app.models.audit_log import AuditLog, ActionType
from app.approval_system.notification_service import NotificationService

logger = logging.getLogger(__name__)

class ApprovalStatus(Enum):
    """Status of an approval request"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ApprovalRequestService:
    """Service for managing approval requests"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.approval_timeout_minutes = 30  # Default timeout: 30 minutes
    
    def create_approval_request(
        self,
        incident_id: int,
        commands: List[str],
        reason: str = "Commands not in allowed list",
        timeout_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create an approval request for filtered commands
        
        Returns:
            dict with request_id, status, and notification results
        """
        try:
            with db_service.get_session() as session:
                incident = session.query(Incident).filter(Incident.id == incident_id).first()
                if not incident:
                    logger.error(f"Incident {incident_id} not found for approval request")
                    return {'success': False, 'error': 'Incident not found'}
                
                # Mark incident as requiring approval
                incident.requires_approval = True
                incident.approval_requested = True
                incident.approval_granted = False
                incident.approval_notes = json.dumps({
                    'commands': commands,
                    'reason': reason,
                    'requested_at': datetime.now().isoformat(),
                    'timeout_minutes': timeout_minutes or self.approval_timeout_minutes
                })
                
                # Send notifications
                notification_results = self.notification_service.send_approval_request(
                    incident_id=incident_id,
                    incident_title=incident.title,
                    commands=commands,
                    reason=reason
                )
                
                # Log the approval request
                audit_log = AuditLog(
                    action_type=ActionType.APPROVAL_REQUESTED,
                    action_description=f"Approval requested for {len(commands)} command(s) not in allowed list",
                    incident_id=incident_id,
                    request_data=json.dumps({
                        'commands': commands,
                        'reason': reason,
                        'notification_results': notification_results
                    }),
                    success=True,
                    user_id="auto_fix_service",
                    source_system="approval_system"
                )
                session.add(audit_log)
                session.commit()
                
                logger.info(f"Created approval request for incident {incident_id}: {len(commands)} commands")
                
                return {
                    'success': True,
                    'incident_id': incident_id,
                    'commands': commands,
                    'notification_results': notification_results,
                    'timeout_minutes': timeout_minutes or self.approval_timeout_minutes
                }
        
        except Exception as e:
            logger.error(f"Error creating approval request: {e}")
            return {'success': False, 'error': str(e)}
    
    def check_approval_status(self, incident_id: int) -> Dict[str, Any]:
        """Check if approval has been granted for an incident"""
        try:
            with db_service.get_session() as session:
                incident = session.query(Incident).filter(Incident.id == incident_id).first()
                if not incident:
                    return {'status': ApprovalStatus.EXPIRED.value, 'approved': False}
                
                if not incident.approval_requested:
                    return {'status': ApprovalStatus.PENDING.value, 'approved': False}
                
                if incident.approval_granted:
                    return {
                        'status': ApprovalStatus.APPROVED.value,
                        'approved': True,
                        'approver': incident.approver,
                        'approved_at': incident.updated_at.isoformat() if incident.updated_at else None
                    }
                
                # Check if expired
                if incident.approval_notes:
                    try:
                        notes = json.loads(incident.approval_notes)
                        requested_at_str = notes.get('requested_at')
                        timeout_minutes = notes.get('timeout_minutes', self.approval_timeout_minutes)
                        
                        if requested_at_str:
                            requested_at = datetime.fromisoformat(requested_at_str)
                            expiry_time = requested_at + timedelta(minutes=timeout_minutes)
                            
                            if datetime.now() > expiry_time:
                                # Mark as expired
                                incident.approval_requested = False
                                session.commit()
                                return {'status': ApprovalStatus.EXPIRED.value, 'approved': False}
                    except:
                        pass
                
                return {'status': ApprovalStatus.PENDING.value, 'approved': False}
        
        except Exception as e:
            logger.error(f"Error checking approval status: {e}")
            return {'status': ApprovalStatus.PENDING.value, 'approved': False}
    
    def grant_approval(
        self,
        incident_id: int,
        approver: str,
        notes: Optional[str] = None
    ) -> bool:
        """Grant approval for an incident"""
        try:
            with db_service.get_session() as session:
                incident = session.query(Incident).filter(Incident.id == incident_id).first()
                if not incident:
                    logger.error(f"Incident {incident_id} not found for approval")
                    return False
                
                incident.approval_granted = True
                incident.approver = approver
                if notes:
                    incident.approval_notes = notes
                
                # Log the approval
                audit_log = AuditLog(
                    action_type=ActionType.APPROVAL_GRANTED,
                    action_description=f"Approval granted by {approver}",
                    incident_id=incident_id,
                    success=True,
                    user_id=approver,
                    source_system="approval_system"
                )
                session.add(audit_log)
                session.commit()
                
                logger.info(f"Approval granted for incident {incident_id} by {approver}")
                return True
        
        except Exception as e:
            logger.error(f"Error granting approval: {e}")
            return False
    
    def reject_approval(
        self,
        incident_id: int,
        rejector: str,
        reason: Optional[str] = None
    ) -> bool:
        """Reject approval for an incident"""
        try:
            with db_service.get_session() as session:
                incident = session.query(Incident).filter(Incident.id == incident_id).first()
                if not incident:
                    return False
                
                incident.approval_requested = False
                incident.approval_granted = False
                if reason:
                    incident.approval_notes = f"Rejected by {rejector}: {reason}"
                
                # Log the rejection
                audit_log = AuditLog(
                    action_type=ActionType.APPROVAL_DENIED,
                    action_description=f"Approval rejected by {rejector}" + (f": {reason}" if reason else ""),
                    incident_id=incident_id,
                    success=False,
                    user_id=rejector,
                    source_system="approval_system"
                )
                session.add(audit_log)
                session.commit()
                
                logger.info(f"Approval rejected for incident {incident_id} by {rejector}")
                return True
        
        except Exception as e:
            logger.error(f"Error rejecting approval: {e}")
            return False

