"""Polling monitor for infrastructure health checks"""

import threading
import time
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import schedule

from config.settings import settings
from app.monitoring.command_executor import CommandExecutor, CommandResult
from app.models.incident import Incident, IncidentStatus, IncidentSeverity
from app.models.audit_log import AuditLog, ActionType
from app.database.database import db_service
from app.services.auto_fix_service import AutoFixService

logger = logging.getLogger(__name__)

# How often to re-check open incidents to see if the issue still exists (seconds)
OPEN_INCIDENT_RECHECK_INTERVAL = 60

@dataclass
class MonitoringCheck:
    """Configuration for a monitoring check"""
    name: str
    command: str
    check_function: Callable[[CommandResult], List[Dict[str, Any]]]
    interval_seconds: int
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    enabled: bool = True

class PollingMonitor:
    """Monitors infrastructure through polling at regular intervals"""
    
    def __init__(self):
        self.command_executor = CommandExecutor()
        self.auto_fix_service = AutoFixService()
        self.is_running = False
        self.monitor_thread = None
        self.checks: List[MonitoringCheck] = []
        self.last_check_times: Dict[str, datetime] = {}
        self.last_open_incident_recheck: Optional[datetime] = None

        # Initialize default monitoring checks
        self._initialize_checks()
    
    def _initialize_checks(self):
        """Initialize default monitoring checks"""
        self.checks = [
            MonitoringCheck(
                name="kubernetes_pods",
                command="kubectl get pods --all-namespaces -o json",
                check_function=self._check_kubernetes_pods,
                interval_seconds=settings.POLLING_INTERVAL,
                severity=IncidentSeverity.HIGH
            ),
            MonitoringCheck(
                name="kubernetes_nodes", 
                command="kubectl get nodes -o json",
                check_function=self._check_kubernetes_nodes,
                interval_seconds=settings.POLLING_INTERVAL,
                severity=IncidentSeverity.CRITICAL
            ),
            MonitoringCheck(
                name="kubernetes_services",
                command="kubectl get services --all-namespaces -o json",
                check_function=self._check_kubernetes_services,
                interval_seconds=settings.POLLING_INTERVAL * 2,  # Less frequent
                severity=IncidentSeverity.MEDIUM
            )
        ]
        
        # Add AWS checks if configured
        if settings.AWS_PROFILE:
            self.checks.append(
                MonitoringCheck(
                    name="aws_ec2_instances",
                    command=f"aws ec2 describe-instances --profile {settings.AWS_PROFILE} --output json",
                    check_function=self._check_aws_ec2,
                    interval_seconds=settings.POLLING_INTERVAL * 3,  # Less frequent for cloud
                    severity=IncidentSeverity.HIGH
                )
            )
        
        # Add GCP checks if configured
        if settings.GCP_PROJECT:
            self.checks.append(
                MonitoringCheck(
                    name="gcp_compute_instances",
                    command=f"gcloud compute instances list --project={settings.GCP_PROJECT} --format=json",
                    check_function=self._check_gcp_instances,
                    interval_seconds=settings.POLLING_INTERVAL * 3,
                    severity=IncidentSeverity.HIGH
                )
            )
        
        # Add Azure checks if configured  
        if settings.AZURE_SUBSCRIPTION:
            self.checks.append(
                MonitoringCheck(
                    name="azure_virtual_machines",
                    command=f"az vm list --subscription {settings.AZURE_SUBSCRIPTION} --output json",
                    check_function=self._check_azure_vms,
                    interval_seconds=settings.POLLING_INTERVAL * 3,
                    severity=IncidentSeverity.HIGH
                )
            )
    
    def start(self):
        """Start the polling monitor"""
        if self.is_running:
            logger.warning("Polling monitor is already running")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Polling monitor started")
        self._log_action("Polling monitor started", ActionType.MONITORING_CHECK)
    
    def stop(self):
        """Stop the polling monitor"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join()
        
        logger.info("Polling monitor stopped")
        self._log_action("Polling monitor stopped", ActionType.MONITORING_CHECK)
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        logger.info("Monitor loop started")
        
        while self.is_running:
            try:
                current_time = datetime.now()
                
                for check in self.checks:
                    if not check.enabled:
                        continue
                    
                    # Check if it's time to run this check
                    last_check = self.last_check_times.get(check.name)
                    if (last_check is None or 
                        (current_time - last_check).total_seconds() >= check.interval_seconds):
                        
                        self._run_check(check)
                        self.last_check_times[check.name] = current_time
                
                # Re-check open incidents every minute: if issue no longer exists, mark resolved
                if (self.last_open_incident_recheck is None or
                    (current_time - self.last_open_incident_recheck).total_seconds() >= OPEN_INCIDENT_RECHECK_INTERVAL):
                    try:
                        self._recheck_open_incidents()
                        self.last_open_incident_recheck = current_time
                    except Exception as e:
                        logger.error(f"Error rechecking open incidents: {str(e)}")
                
                # Sleep for a short interval before next iteration
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {str(e)}")
                time.sleep(60)  # Sleep longer on error
    
    def _run_check(self, check: MonitoringCheck):
        """Run a specific monitoring check"""
        try:
            logger.info(f"Running check: {check.name}")
            
            # Execute the command
            result = self.command_executor.execute_command(check.command)
            
            if not result.success:
                # Command failed - create incident
                self._create_incident(
                    title=f"Monitoring command failed: {check.name}",
                    description=f"Command '{check.command}' failed with exit code {result.exit_code}\nError: {result.stderr}",
                    severity=check.severity,
                    source_system=self._get_system_from_command(check.command),
                    error_message=result.stderr
                )
                return
            
            # Run the check function to analyze results
            issues = check.check_function(result)
            
            # Create incidents for any issues found
            for issue in issues:
                self._create_incident_from_issue(issue, check.severity)
            
            logger.info(f"Check {check.name} completed. Found {len(issues)} issues.")
            
        except Exception as e:
            logger.error(f"Error running check {check.name}: {str(e)}")
            self._create_incident(
                title=f"Monitoring check error: {check.name}",
                description=f"Exception occurred while running check: {str(e)}",
                severity=IncidentSeverity.HIGH,
                source_system="monitoring"
            )
    
    def _check_kubernetes_pods(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check Kubernetes pods for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for pod in data.get('items', []):
                metadata = pod.get('metadata', {})
                status = pod.get('status', {})
                
                pod_name = metadata.get('name', 'unknown')
                namespace = metadata.get('namespace', 'unknown')
                phase = status.get('phase', 'Unknown')
                
                # Check for unhealthy pods
                if phase not in ['Running', 'Succeeded']:
                    container_statuses = status.get('containerStatuses', [])
                    
                    issue = {
                        'type': 'pod_unhealthy',
                        'title': f"Pod {pod_name} is {phase}",
                        'description': f"Pod {pod_name} in namespace {namespace} is in {phase} state",
                        'pod_name': pod_name,
                        'namespace': namespace,
                        'phase': phase,
                        'reason': status.get('reason'),
                        'message': status.get('message')
                    }
                    
                    # Add container details
                    if container_statuses:
                        container_issues = []
                        for container in container_statuses:
                            if not container.get('ready', False):
                                waiting = container.get('state', {}).get('waiting', {})
                                terminated = container.get('state', {}).get('terminated', {})
                                
                                if waiting:
                                    container_issues.append(f"Container {container.get('name')}: {waiting.get('reason')} - {waiting.get('message')}")
                                elif terminated:
                                    container_issues.append(f"Container {container.get('name')}: Terminated with exit code {terminated.get('exitCode')} - {terminated.get('reason')}")
                        
                        if container_issues:
                            issue['description'] += "\\n\\nContainer issues:\\n" + "\\n".join(container_issues)
                    
                    issues.append(issue)
                
                # Check for high restart counts
                container_statuses = status.get('containerStatuses', [])
                for container in container_statuses:
                    restart_count = container.get('restartCount', 0)
                    if restart_count > 5:  # Threshold for concern
                        issues.append({
                            'type': 'high_restart_count',
                            'title': f"High restart count for container {container.get('name')} in pod {pod_name}",
                            'description': f"Container {container.get('name')} in pod {pod_name} (namespace: {namespace}) has restarted {restart_count} times",
                            'pod_name': pod_name,
                            'namespace': namespace,
                            'container_name': container.get('name'),
                            'restart_count': restart_count
                        })
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl pods output: {str(e)}")
        
        return issues
    
    def _check_kubernetes_nodes(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check Kubernetes nodes for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for node in data.get('items', []):
                metadata = node.get('metadata', {})
                status = node.get('status', {})
                
                node_name = metadata.get('name', 'unknown')
                conditions = status.get('conditions', [])
                
                # Check node conditions
                for condition in conditions:
                    condition_type = condition.get('type')
                    condition_status = condition.get('status')
                    
                    if condition_type == 'Ready' and condition_status != 'True':
                        issues.append({
                            'type': 'node_not_ready',
                            'title': f"Node {node_name} is not Ready",
                            'description': f"Node {node_name} condition '{condition_type}' is '{condition_status}'. Reason: {condition.get('reason')}. Message: {condition.get('message')}",
                            'node_name': node_name,
                            'condition_type': condition_type,
                            'condition_status': condition_status,
                            'reason': condition.get('reason'),
                            'message': condition.get('message')
                        })
                    
                    elif condition_type in ['DiskPressure', 'MemoryPressure', 'PIDPressure'] and condition_status == 'True':
                        issues.append({
                            'type': 'node_pressure',
                            'title': f"Node {node_name} has {condition_type}",
                            'description': f"Node {node_name} is experiencing {condition_type}. Message: {condition.get('message')}",
                            'node_name': node_name,
                            'condition_type': condition_type,
                            'message': condition.get('message')
                        })
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl nodes output: {str(e)}")
        
        return issues
    
    def _check_kubernetes_services(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check Kubernetes services for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for service in data.get('items', []):
                metadata = service.get('metadata', {})
                spec = service.get('spec', {})
                
                service_name = metadata.get('name', 'unknown')
                namespace = metadata.get('namespace', 'unknown')
                service_type = spec.get('type', 'ClusterIP')
                
                # Check for LoadBalancer services without external IP
                if service_type == 'LoadBalancer':
                    status = service.get('status', {})
                    ingress = status.get('loadBalancer', {}).get('ingress', [])
                    
                    if not ingress:
                        issues.append({
                            'type': 'loadbalancer_no_external_ip',
                            'title': f"LoadBalancer service {service_name} has no external IP",
                            'description': f"LoadBalancer service {service_name} in namespace {namespace} has been created but no external IP has been assigned",
                            'service_name': service_name,
                            'namespace': namespace,
                            'service_type': service_type
                        })
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse kubectl services output: {str(e)}")
        
        return issues
    
    def _check_aws_ec2(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check AWS EC2 instances for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for reservation in data.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instance_id = instance.get('InstanceId', 'unknown')
                    state = instance.get('State', {}).get('Name', 'unknown')
                    instance_type = instance.get('InstanceType', 'unknown')
                    
                    # Check for stopped instances
                    if state in ['stopped', 'stopping', 'terminated', 'terminating']:
                        issues.append({
                            'type': 'ec2_instance_down',
                            'title': f"EC2 instance {instance_id} is {state}",
                            'description': f"EC2 instance {instance_id} ({instance_type}) is in {state} state",
                            'instance_id': instance_id,
                            'state': state,
                            'instance_type': instance_type
                        })
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AWS EC2 output: {str(e)}")
        
        return issues
    
    def _check_gcp_instances(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check GCP Compute Engine instances for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for instance in data:
                name = instance.get('name', 'unknown')
                status = instance.get('status', 'unknown')
                zone = instance.get('zone', 'unknown').split('/')[-1]  # Extract zone name from URL
                
                # Check for non-running instances
                if status != 'RUNNING':
                    issues.append({
                        'type': 'gce_instance_down',
                        'title': f"GCE instance {name} is {status}",
                        'description': f"GCE instance {name} in zone {zone} is {status}",
                        'instance_name': name,
                        'status': status,
                        'zone': zone
                    })
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GCP instances output: {str(e)}")
        
        return issues
    
    def _check_azure_vms(self, result: CommandResult) -> List[Dict[str, Any]]:
        """Check Azure Virtual Machines for issues"""
        issues = []
        
        try:
            data = json.loads(result.stdout)
            
            for vm in data:
                name = vm.get('name', 'unknown')
                resource_group = vm.get('resourceGroup', 'unknown')
                
                # Note: Basic listing doesn't include power state
                # Would need additional call to get-instance-view for detailed status
                # For now, we'll assume VMs in the list are provisioned
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Azure VMs output: {str(e)}")
        
        return issues
    
    def _create_incident_from_issue(self, issue: Dict[str, Any], severity: IncidentSeverity):
        """Create an incident from a detected issue"""
        self._create_incident(
            title=issue.get('title', 'Unknown issue'),
            description=issue.get('description', 'No description available'),
            severity=severity,
            source_system=issue.get('source_system', 'kubernetes'),
            affected_service=issue.get('pod_name') or issue.get('service_name') or issue.get('instance_id') or issue.get('instance_name') or issue.get('node_name'),
            namespace=issue.get('namespace'),
            error_message=issue.get('message')
        )
    
    def _create_incident(
        self,
        title: str,
        description: str,
        severity: IncidentSeverity,
        source_system: str,
        affected_service: Optional[str] = None,
        namespace: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Create a new incident"""
        try:
            with db_service.get_session() as session:
                # Check if similar incident already exists and is open
                existing_incident = session.query(Incident).filter(
                    Incident.title == title,
                    Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS])
                ).first()
                
                if existing_incident:
                    logger.info(f"Similar incident already exists: {existing_incident.id}")
                    # Attempt auto-fix if not already attempted
                    if not existing_incident.auto_fix_attempted:
                        try:
                            logger.info(f"Attempting auto-fix for existing incident {existing_incident.id}")
                            self.auto_fix_service.attempt_auto_fix(existing_incident)
                        except Exception as e:
                            logger.error(f"Error during auto-fix attempt for existing incident: {str(e)}")
                    return
                
                incident = Incident(
                    title=title,
                    description=description,
                    severity=severity,
                    status=IncidentStatus.OPEN,
                    source="polling",
                    source_system=source_system,
                    affected_service=affected_service,
                    namespace=namespace,
                    error_message=error_message
                )
                
                session.add(incident)
                session.commit()
                
                logger.info(f"Created incident: {incident.id} - {title}")
                self._log_action(f"Created incident: {title}", ActionType.INCIDENT_CREATED)
                
                # Attempt auto-fix for the newly created incident
                try:
                    logger.info(f"Attempting auto-fix for incident {incident.id}")
                    self.auto_fix_service.attempt_auto_fix(incident)
                except Exception as e:
                    logger.error(f"Error during auto-fix attempt: {str(e)}")
                
        except Exception as e:
            logger.error(f"Failed to create incident: {str(e)}")
    
    def _get_system_from_command(self, command: str) -> str:
        """Determine source system from command"""
        if command.startswith('kubectl'):
            return 'kubernetes'
        elif command.startswith('aws'):
            return 'aws'
        elif command.startswith('gcloud'):
            return 'gcp'
        elif command.startswith('az'):
            return 'azure'
        else:
            return 'unknown'

    def _recheck_open_incidents(self):
        """Re-check all open incidents every minute; mark resolved if the issue no longer exists."""
        try:
            with db_service.get_session() as session:
                open_incidents = session.query(Incident).filter(
                    Incident.status.in_([IncidentStatus.OPEN, IncidentStatus.IN_PROGRESS])
                ).all()
                if not open_incidents:
                    return
                for incident in open_incidents:
                    try:
                        if not self._issue_still_exists(incident):
                            incident.status = IncidentStatus.RESOLVED
                            incident.resolved_at = datetime.now()
                            session.commit()
                            logger.info(f"Incident {incident.id} marked resolved (issue no longer exists): {incident.title}")
                            self._log_action(
                                f"Incident {incident.id} auto-resolved: issue no longer detected",
                                ActionType.INCIDENT_RESOLVED,
                                incident.id
                            )
                    except Exception as e:
                        logger.warning(f"Error rechecking incident {incident.id}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to recheck open incidents: {str(e)}")
            raise

    def _issue_still_exists(self, incident: Incident) -> bool:
        """
        Return True if the underlying issue for this incident still exists, False if it is gone.
        Used to auto-resolve when the condition that created the incident has cleared.
        """
        title = (incident.title or "").strip()
        source_system = (incident.source_system or "").lower()
        affected = (incident.affected_service or "").strip()
        namespace = (incident.namespace or "default").strip()

        # Monitoring command failed: re-run the same command; if it succeeds, issue is gone
        if title.startswith("Monitoring command failed:"):
            check_name = title.replace("Monitoring command failed:", "").strip()
            for check in self.checks:
                if check.name == check_name and check.enabled:
                    result = self.command_executor.execute_command(check.command)
                    return not result.success
            return True  # Unknown check or disabled: assume still exists

        # Kubernetes: re-run the relevant check and see if this resource still appears in issues
        if source_system == "kubernetes":
            if "pod" in title.lower() and affected:
                # Re-run full pods check; if this pod still appears in issues list, it's still open
                result = self.command_executor.execute_command("kubectl get pods --all-namespaces -o json")
                if not result.success:
                    return True  # Can't verify, assume still exists
                issues = self._check_kubernetes_pods(result)
                for issue in issues:
                    if issue.get("pod_name") == affected and issue.get("namespace") == namespace:
                        return True  # Same pod still has an issue
                return False  # No issue found for this pod
            if "node" in title.lower() and affected:
                result = self.command_executor.execute_command("kubectl get nodes -o json")
                if not result.success:
                    return True
                issues = self._check_kubernetes_nodes(result)
                for issue in issues:
                    if issue.get("node_name") == affected:
                        return True
                return False
            if "service" in title.lower() or "loadbalancer" in title.lower():
                result = self.command_executor.execute_command("kubectl get services --all-namespaces -o json")
                if not result.success:
                    return True
                issues = self._check_kubernetes_services(result)
                for issue in issues:
                    if issue.get("service_name") == affected and issue.get("namespace") == namespace:
                        return True
                return False
            # Generic k8s: assume still exists if we can't recheck
            return True

        # AWS EC2
        if source_system == "aws" and affected:
            cmd = f"aws ec2 describe-instances --instance-ids {affected} --output json"
            if getattr(settings, "AWS_PROFILE", None):
                cmd = f"aws ec2 describe-instances --instance-ids {affected} --profile {settings.AWS_PROFILE} --output json"
            result = self.command_executor.execute_command(cmd)
            if not result.success:
                return False  # Instance not found or command error - treat as resolved
            try:
                data = json.loads(result.stdout)
                instances = data.get("Reservations", [])
                for res in instances:
                    for inst in res.get("Instances", []):
                        if inst.get("InstanceId") == affected:
                            state = inst.get("State", {}).get("Name", "")
                            return state not in ("running",)
                return False
            except (json.JSONDecodeError, KeyError):
                return True

        # GCP
        if source_system == "gcp" and affected:
            if getattr(settings, "GCP_PROJECT", None):
                result = self.command_executor.execute_command(
                    f"gcloud compute instances describe {affected} --project={settings.GCP_PROJECT} --format=json"
                )
            else:
                result = self.command_executor.execute_command(
                    f"gcloud compute instances describe {affected} --format=json"
                )
            if not result.success:
                return False
            try:
                data = json.loads(result.stdout)
                status = data.get("status", "")
                return status != "RUNNING"
            except (json.JSONDecodeError, KeyError):
                return True

        # Webhook / unknown: do not auto-resolve
        return True

    def _log_action(self, description: str, action_type: ActionType, incident_id: Optional[int] = None):
        """Log action to audit log"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=action_type,
                    action_description=description,
                    success=True,
                    user_id="polling_monitor",
                    source_system="monitoring",
                    incident_id=incident_id
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {str(e)}")
    
    def add_custom_check(self, check: MonitoringCheck):
        """Add a custom monitoring check"""
        self.checks.append(check)
        logger.info(f"Added custom check: {check.name}")
    
    def remove_check(self, check_name: str):
        """Remove a monitoring check"""
        self.checks = [c for c in self.checks if c.name != check_name]
        logger.info(f"Removed check: {check_name}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get monitor status"""
        return {
            'is_running': self.is_running,
            'enabled_checks': len([c for c in self.checks if c.enabled]),
            'total_checks': len(self.checks),
            'last_check_times': {name: time.isoformat() if time else None 
                               for name, time in self.last_check_times.items()},
            'checks': [
                {
                    'name': c.name,
                    'enabled': c.enabled,
                    'interval_seconds': c.interval_seconds,
                    'severity': c.severity.value
                }
                for c in self.checks
            ]
        }