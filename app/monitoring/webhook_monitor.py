"""Webhook monitor for receiving incident alerts from external systems"""

import threading
import json
import logging
import hmac
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
from flask import Flask, request, jsonify
from werkzeug.serving import make_server
import signal
import sys

from config.settings import settings
from app.models.incident import Incident, IncidentStatus, IncidentSeverity
from app.models.audit_log import AuditLog, ActionType
from app.database.database import db_service
from app.services.auto_fix_service import AutoFixService

logger = logging.getLogger(__name__)

class WebhookMonitor:
    """Receives and processes webhook alerts from monitoring systems"""
    
    def __init__(self, port: int = None, secret: str = None):
        self.port = port or settings.WEBHOOK_PORT
        self.secret = secret or settings.WEBHOOK_SECRET
        self.app = Flask(__name__)
        self.server = None
        self.is_running = False
        self.auto_fix_service = AutoFixService()
        
        # Setup routes
        self._setup_routes()
        
        # Supported webhook formats
        self.webhook_processors = {
            'prometheus': self._process_prometheus_webhook,
            'grafana': self._process_grafana_webhook,
            'alertmanager': self._process_alertmanager_webhook,
            'kubernetes': self._process_kubernetes_webhook,
            'generic': self._process_generic_webhook
        }
    
    def _setup_routes(self):
        """Setup Flask routes for webhook endpoints"""
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook_generic():
            return self._handle_webhook('generic')
        
        @self.app.route('/webhook/prometheus', methods=['POST'])
        def webhook_prometheus():
            return self._handle_webhook('prometheus')
        
        @self.app.route('/webhook/grafana', methods=['POST'])
        def webhook_grafana():
            return self._handle_webhook('grafana')
        
        @self.app.route('/webhook/alertmanager', methods=['POST'])
        def webhook_alertmanager():
            return self._handle_webhook('alertmanager')
        
        @self.app.route('/webhook/kubernetes', methods=['POST'])
        def webhook_kubernetes():
            return self._handle_webhook('kubernetes')
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'version': settings.APP_VERSION
            })
        
        @self.app.route('/status', methods=['GET'])
        def status():
            return jsonify(self.get_status())
    
    def _handle_webhook(self, webhook_type: str):
        """Handle incoming webhook"""
        try:
            # Get request data
            payload = request.get_json()
            headers = dict(request.headers)
            
            # Verify webhook signature if secret is configured
            if self.secret and not self._verify_signature(request.data, headers.get('X-Hub-Signature-256')):
                logger.warning("Webhook signature verification failed")
                return jsonify({'error': 'Invalid signature'}), 401
            
            # Log webhook reception
            self._log_webhook_received(webhook_type, payload)
            
            # Process webhook based on type
            processor = self.webhook_processors.get(webhook_type, self._process_generic_webhook)
            incidents = processor(payload, headers)
            
            # Create incidents for each alert
            created_incidents = []
            for incident_data in incidents:
                incident = self._create_incident(incident_data)
                if incident:
                    created_incidents.append(incident.id)
            
            response = {
                'status': 'success',
                'webhook_type': webhook_type,
                'incidents_created': len(created_incidents),
                'incident_ids': created_incidents,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Processed {webhook_type} webhook, created {len(created_incidents)} incidents")
            return jsonify(response)
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return jsonify({
                'error': 'Failed to process webhook',
                'details': str(e)
            }), 500
    
    def _verify_signature(self, payload: bytes, signature: Optional[str]) -> bool:
        """Verify webhook signature"""
        if not signature or not self.secret:
            return not self.secret  # If no secret configured, allow
        
        try:
            # GitHub style signature
            expected_signature = 'sha256=' + hmac.new(
                self.secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}")
            return False
    
    def _process_prometheus_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process Prometheus webhook format"""
        incidents = []
        
        try:
            # Prometheus/Alertmanager format
            alerts = payload.get('alerts', [])
            
            for alert in alerts:
                status = alert.get('status', 'firing')
                if status != 'firing':
                    continue  # Skip resolved alerts for now
                
                labels = alert.get('labels', {})
                annotations = alert.get('annotations', {})
                
                incident = {
                    'title': labels.get('alertname', 'Prometheus Alert'),
                    'description': annotations.get('description') or annotations.get('summary') or 'No description available',
                    'severity': self._map_prometheus_severity(labels.get('severity', 'warning')),
                    'source_system': 'prometheus',
                    'affected_service': labels.get('service') or labels.get('job'),
                    'namespace': labels.get('namespace'),
                    'error_message': annotations.get('message'),
                    'webhook_payload': json.dumps(alert),
                    'labels': labels,
                    'annotations': annotations
                }
                
                incidents.append(incident)
                
        except Exception as e:
            logger.error(f"Error processing Prometheus webhook: {str(e)}")
        
        return incidents
    
    def _process_grafana_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process Grafana webhook format"""
        incidents = []
        
        try:
            # Grafana alert format
            alerts = payload.get('alerts', [])
            
            for alert in alerts:
                state = alert.get('state', 'alerting')
                if state != 'alerting':
                    continue
                
                incident = {
                    'title': alert.get('name', 'Grafana Alert'),
                    'description': alert.get('message', 'No description available'),
                    'severity': self._map_grafana_severity(state),
                    'source_system': 'grafana',
                    'affected_service': alert.get('tags', {}).get('service'),
                    'error_message': alert.get('message'),
                    'webhook_payload': json.dumps(alert)
                }
                
                incidents.append(incident)
                
        except Exception as e:
            logger.error(f"Error processing Grafana webhook: {str(e)}")
        
        return incidents
    
    def _process_alertmanager_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process Alertmanager webhook format"""
        # Alertmanager uses similar format to Prometheus
        return self._process_prometheus_webhook(payload, headers)
    
    def _process_kubernetes_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process Kubernetes event webhook format"""
        incidents = []
        
        try:
            # Kubernetes event format
            event_type = payload.get('type', 'Normal')
            if event_type == 'Normal':
                return incidents  # Skip normal events
            
            object_info = payload.get('object', {})
            involved_object = object_info.get('involvedObject', {})
            
            incident = {
                'title': f"Kubernetes {event_type}: {object_info.get('reason', 'Unknown')}",
                'description': object_info.get('message', 'No description available'),
                'severity': self._map_kubernetes_severity(event_type, object_info.get('reason')),
                'source_system': 'kubernetes',
                'affected_service': involved_object.get('name'),
                'namespace': involved_object.get('namespace'),
                'error_message': object_info.get('message'),
                'webhook_payload': json.dumps(payload)
            }
            
            incidents.append(incident)
            
        except Exception as e:
            logger.error(f"Error processing Kubernetes webhook: {str(e)}")
        
        return incidents
    
    def _process_generic_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process generic webhook format"""
        incidents = []
        
        try:
            # Try to extract common fields
            incident = {
                'title': payload.get('title') or payload.get('alert') or payload.get('name') or 'Generic Alert',
                'description': payload.get('description') or payload.get('message') or payload.get('summary') or str(payload),
                'severity': self._map_generic_severity(payload.get('severity') or payload.get('level') or 'medium'),
                'source_system': payload.get('source') or payload.get('system') or 'external',
                'affected_service': payload.get('service') or payload.get('component'),
                'namespace': payload.get('namespace'),
                'error_message': payload.get('error') or payload.get('message'),
                'webhook_payload': json.dumps(payload)
            }
            
            incidents.append(incident)
            
        except Exception as e:
            logger.error(f"Error processing generic webhook: {str(e)}")
        
        return incidents
    
    def _map_prometheus_severity(self, severity: str) -> IncidentSeverity:
        """Map Prometheus severity to IncidentSeverity"""
        severity_map = {
            'critical': IncidentSeverity.CRITICAL,
            'high': IncidentSeverity.HIGH,
            'warning': IncidentSeverity.MEDIUM,
            'info': IncidentSeverity.LOW,
            'low': IncidentSeverity.LOW
        }
        return severity_map.get(severity.lower(), IncidentSeverity.MEDIUM)
    
    def _map_grafana_severity(self, state: str) -> IncidentSeverity:
        """Map Grafana alert state to IncidentSeverity"""
        if state == 'alerting':
            return IncidentSeverity.HIGH
        return IncidentSeverity.MEDIUM
    
    def _map_kubernetes_severity(self, event_type: str, reason: str) -> IncidentSeverity:
        """Map Kubernetes event to IncidentSeverity"""
        if event_type == 'Warning':
            critical_reasons = ['Failed', 'FailedScheduling', 'FailedMount', 'ImagePullBackOff', 'CrashLoopBackOff']
            if any(r in reason for r in critical_reasons):
                return IncidentSeverity.CRITICAL
            return IncidentSeverity.HIGH
        return IncidentSeverity.MEDIUM
    
    def _map_generic_severity(self, severity: str) -> IncidentSeverity:
        """Map generic severity string to IncidentSeverity"""
        severity_map = {
            'critical': IncidentSeverity.CRITICAL,
            'high': IncidentSeverity.HIGH,
            'medium': IncidentSeverity.MEDIUM,
            'low': IncidentSeverity.LOW,
            'error': IncidentSeverity.HIGH,
            'warning': IncidentSeverity.MEDIUM,
            'info': IncidentSeverity.LOW
        }
        return severity_map.get(severity.lower(), IncidentSeverity.MEDIUM)
    
    def _create_incident(self, incident_data: Dict[str, Any]) -> Optional[Incident]:
        """Create incident from webhook data"""
        try:
            with db_service.get_session() as session:
                # Check for duplicate incidents
                existing_incident = session.query(Incident).filter(
                    Incident.title == incident_data['title'],
                    Incident.source_system == incident_data['source_system'],
                    Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS])
                ).first()
                
                if existing_incident:
                    logger.info(f"Similar incident already exists: {existing_incident.id}")
                    # Update the existing incident with new webhook data
                    existing_incident.webhook_payload = incident_data.get('webhook_payload')
                    existing_incident.updated_at = datetime.now()
                    session.commit()
                    return existing_incident
                
                incident = Incident(
                    title=incident_data['title'],
                    description=incident_data['description'],
                    severity=incident_data['severity'],
                    status=IncidentStatus.OPEN,
                    source="webhook",
                    source_system=incident_data['source_system'],
                    affected_service=incident_data.get('affected_service'),
                    namespace=incident_data.get('namespace'),
                    error_message=incident_data.get('error_message'),
                    webhook_payload=incident_data.get('webhook_payload')
                )
                
                session.add(incident)
                session.commit()
                
                logger.info(f"Created incident from webhook: {incident.id} - {incident.title}")
                self._log_action(f"Created incident from webhook: {incident.title}", ActionType.INCIDENT_CREATED)
                
                # Attempt auto-fix for the newly created incident
                try:
                    logger.info(f"Attempting auto-fix for incident {incident.id}")
                    self.auto_fix_service.attempt_auto_fix(incident)
                except Exception as e:
                    logger.error(f"Error during auto-fix attempt: {str(e)}")
                
                return incident
                
        except Exception as e:
            logger.error(f"Failed to create incident from webhook: {str(e)}")
            return None
    
    def _log_webhook_received(self, webhook_type: str, payload: Dict[str, Any]):
        """Log webhook reception"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=ActionType.WEBHOOK_RECEIVED,
                    action_description=f"Received {webhook_type} webhook",
                    request_data=json.dumps(payload),
                    success=True,
                    user_id="webhook_monitor",
                    source_system=webhook_type
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log webhook reception: {str(e)}")
    
    def _log_action(self, description: str, action_type: ActionType):
        """Log action to audit log"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=action_type,
                    action_description=description,
                    success=True,
                    user_id="webhook_monitor",
                    source_system="webhook"
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {str(e)}")
    
    def start(self):
        """Start the webhook server"""
        if self.is_running:
            logger.warning("Webhook monitor is already running")
            return
        
        original_port = self.port
        
        # Try to find an available port if the configured port is in use
        for attempt in range(10):  # Try up to 10 alternative ports
            try:
                # Try to create the server - this will fail if port is in use
                # Note: werkzeug catches OSError and calls sys.exit(1), so we catch SystemExit
                self.server = make_server('0.0.0.0', self.port, self.app, threaded=True)
                self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
                self.server_thread.start()
                self.is_running = True
                
                if self.port != original_port:
                    logger.warning(f"Port {original_port} was in use, using port {self.port} instead")
                else:
                    logger.info(f"Webhook monitor started on port {self.port}")
                
                self._log_action("Webhook monitor started", ActionType.MONITORING_CHECK)
                return
                
            except (OSError, SystemExit) as e:
                # werkzeug catches OSError and raises SystemExit(1), so we catch both
                error_str = str(e).lower() if hasattr(e, '__str__') else ''
                errno = getattr(e, 'errno', None)
                
                # Check if it's a port in use error
                is_port_in_use = (
                    "address already in use" in error_str or 
                    errno == 98 or  # Linux: Address already in use
                    errno == 48 or  # macOS: Address already in use
                    isinstance(e, SystemExit)  # werkzeug calls sys.exit(1) on port conflict
                )
                
                if is_port_in_use:
                    # Port is in use, try next one
                    if attempt == 0:
                        logger.warning(f"Port {self.port} is already in use, trying alternative ports...")
                    self.port += 1
                    continue
                else:
                    # Different error, re-raise it (but convert SystemExit to RuntimeError)
                    if isinstance(e, SystemExit):
                        raise RuntimeError(f"Failed to start webhook monitor on port {self.port}: {error_str}")
                    raise
            except Exception as e:
                if attempt == 0:
                    # First attempt failed, try alternative ports
                    logger.warning(f"Failed to start on port {self.port}: {str(e)}, trying alternative ports...")
                    self.port += 1
                    continue
                else:
                    raise
        
        # If we get here, we couldn't find an available port
        error_msg = f"Failed to start webhook monitor: Could not find an available port (tried {original_port} to {self.port})"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    def stop(self):
        """Stop the webhook server"""
        if not self.is_running:
            return
        
        try:
            if self.server:
                self.server.shutdown()
            self.is_running = False
            
            logger.info("Webhook monitor stopped")
            self._log_action("Webhook monitor stopped", ActionType.MONITORING_CHECK)
            
        except Exception as e:
            logger.error(f"Error stopping webhook monitor: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get webhook monitor status"""
        return {
            'is_running': self.is_running,
            'port': self.port,
            'endpoints': [
                f'http://localhost:{self.port}/webhook',
                f'http://localhost:{self.port}/webhook/prometheus',
                f'http://localhost:{self.port}/webhook/grafana',
                f'http://localhost:{self.port}/webhook/alertmanager',
                f'http://localhost:{self.port}/webhook/kubernetes',
                f'http://localhost:{self.port}/health'
            ],
            'supported_formats': list(self.webhook_processors.keys())
        }
    
    def test_webhook(self, webhook_type: str = 'generic', test_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send test webhook for debugging"""
        test_data = test_data or {
            'title': 'Test Alert',
            'description': 'This is a test alert',
            'severity': 'medium',
            'source': 'test',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            incidents = self.webhook_processors[webhook_type](test_data, {})
            return {
                'status': 'success',
                'incidents_would_be_created': len(incidents),
                'incident_data': incidents
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }