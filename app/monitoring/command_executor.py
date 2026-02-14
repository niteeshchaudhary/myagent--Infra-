"""Command executor for running infrastructure monitoring commands"""

import subprocess
import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import shlex
import os
import tempfile

from config.settings import settings
from app.models.audit_log import AuditLog, ActionType
from app.database.database import db_service

logger = logging.getLogger(__name__)

@dataclass
class CommandResult:
    """Result of command execution"""
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timestamp: datetime
    success: bool

class CommandExecutor:
    """Executes infrastructure monitoring commands safely"""
    
    def __init__(self):
        self.max_execution_time = 300  # 5 minutes default
        # Shorter timeouts for commands that can hang
        self.command_timeouts = {
            'kubectl cluster-info': 30,  # 30 seconds for cluster-info
            'kubectl get': 20,  # 20 seconds for get commands
            'kubectl describe': 30,  # 30 seconds for describe
            'kubectl logs': 20,  # 20 seconds for logs
            'kubectl': 30,  # 30 seconds default for all kubectl commands
        }
        
    def is_command_allowed(self, command: str) -> bool:
        """Check if command is allowed using command list manager (checks both allowed and not-allowed lists)"""
        # Lazy import to avoid circular dependencies
        from app.services.command_list_manager import command_list_manager
        return command_list_manager.is_command_allowed(command)
    
    def _get_command_timeout(self, command: str, timeout: Optional[int] = None) -> int:
        """Get appropriate timeout for a command"""
        if timeout is not None:
            return timeout
        
        # Check for specific command timeouts
        command_lower = command.lower().strip()
        for cmd_pattern, cmd_timeout in self.command_timeouts.items():
            if command_lower.startswith(cmd_pattern.lower()):
                return cmd_timeout
        
        # Default timeout
        return self.max_execution_time
    
    def execute_command(
        self, 
        command: str, 
        timeout: Optional[int] = None,
        log_execution: bool = True
    ) -> CommandResult:
        """Execute a command safely with logging and timeout handling"""
        start_time = time.time()
        timestamp = datetime.now()
        
        if not self.is_command_allowed(command):
            logger.warning(f"Command not allowed: {command}")
            result = CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr="Command not allowed",
                duration_ms=0,
                timestamp=timestamp,
                success=False
            )
            if log_execution:
                self._log_execution(result)
            return result
        
        # Get appropriate timeout for this command
        cmd_timeout = self._get_command_timeout(command, timeout)
        logger.debug(f"Executing command '{command}' with timeout {cmd_timeout}s")
        
        try:
            # Use shell=True on Windows for kubectl, aws, gcloud, az commands
            shell = os.name == 'nt'
            
            process = subprocess.run(
                command if shell else shlex.split(command),
                capture_output=True,
                text=True,
                timeout=cmd_timeout,
                shell=shell,
                env=os.environ.copy()
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            result = CommandResult(
                command=command,
                exit_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
                duration_ms=duration_ms,
                timestamp=timestamp,
                success=process.returncode == 0
            )
            
            if log_execution:
                self._log_execution(result)
            
            logger.info(f"Command executed: {command} (exit_code: {process.returncode}, duration: {duration_ms}ms)")
            return result
            
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # Capture any partial output if available
            partial_stdout = ""
            partial_stderr = ""
            
            if hasattr(e, 'stdout') and e.stdout:
                try:
                    partial_stdout = e.stdout.decode('utf-8', errors='ignore')
                except (AttributeError, UnicodeDecodeError):
                    partial_stdout = str(e.stdout)[:500] if e.stdout else ""
            
            if hasattr(e, 'stderr') and e.stderr:
                try:
                    partial_stderr = e.stderr.decode('utf-8', errors='ignore')
                except (AttributeError, UnicodeDecodeError):
                    partial_stderr = str(e.stderr)[:500] if e.stderr else ""
            
            timeout_error_msg = (
                f"Command timed out after {cmd_timeout} seconds. "
                f"This usually indicates a network connectivity issue or the target service is unreachable. "
                f"Common causes: network timeout, unreachable endpoint, firewall blocking, DNS issues."
            )
            
            if partial_stderr:
                timeout_error_msg += f"\nPartial error output before timeout: {partial_stderr}"
            
            result = CommandResult(
                command=command,
                exit_code=-2,
                stdout=partial_stdout,
                stderr=timeout_error_msg,
                duration_ms=duration_ms,
                timestamp=timestamp,
                success=False
            )
            if log_execution:
                self._log_execution(result)
            logger.warning(f"Command timed out after {cmd_timeout}s: {command}")
            return result
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Command execution error: {str(e)}"
            result = CommandResult(
                command=command,
                exit_code=-3,
                stdout="",
                stderr=error_msg,
                duration_ms=duration_ms,
                timestamp=timestamp,
                success=False
            )
            if log_execution:
                self._log_execution(result)
            logger.error(f"Command execution error: {command} - {error_msg}")
            return result
    
    def _log_execution(self, result: CommandResult):
        """Log command execution to audit log"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=ActionType.COMMAND_EXECUTED,
                    action_description=f"Executed command: {result.command}",
                    command_executed=result.command,
                    command_output=result.stdout,
                    command_exit_code=result.exit_code,
                    success=result.success,
                    error_message=result.stderr if not result.success else None,
                    duration_ms=result.duration_ms,
                    user_id="system",
                    source_system="monitoring"
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log command execution: {str(e)}")
    
    def get_kubernetes_status(self) -> Dict[str, Any]:
        """Get comprehensive Kubernetes cluster status"""
        results = {}
        
        # Get pods status
        pods_result = self.execute_command("kubectl get pods --all-namespaces -o json")
        if pods_result.success:
            try:
                pods_data = json.loads(pods_result.stdout)
                results['pods'] = pods_data
                
                # Analyze pod health
                unhealthy_pods = []
                for pod in pods_data.get('items', []):
                    status = pod.get('status', {})
                    phase = status.get('phase')
                    if phase not in ['Running', 'Succeeded']:
                        unhealthy_pods.append({
                            'name': pod.get('metadata', {}).get('name'),
                            'namespace': pod.get('metadata', {}).get('namespace'),
                            'phase': phase,
                            'reason': status.get('reason'),
                            'message': status.get('message')
                        })
                
                results['unhealthy_pods'] = unhealthy_pods
                
            except json.JSONDecodeError:
                logger.error("Failed to parse kubectl pods output")
        
        # Get nodes status
        nodes_result = self.execute_command("kubectl get nodes -o json")
        if nodes_result.success:
            try:
                nodes_data = json.loads(nodes_result.stdout)
                results['nodes'] = nodes_data
                
                # Check node conditions
                unhealthy_nodes = []
                for node in nodes_data.get('items', []):
                    conditions = node.get('status', {}).get('conditions', [])
                    for condition in conditions:
                        if condition.get('type') == 'Ready' and condition.get('status') != 'True':
                            unhealthy_nodes.append({
                                'name': node.get('metadata', {}).get('name'),
                                'condition': condition.get('type'),
                                'status': condition.get('status'),
                                'reason': condition.get('reason'),
                                'message': condition.get('message')
                            })
                
                results['unhealthy_nodes'] = unhealthy_nodes
                
            except json.JSONDecodeError:
                logger.error("Failed to parse kubectl nodes output")
        
        # Get services status
        services_result = self.execute_command("kubectl get services --all-namespaces -o json")
        if services_result.success:
            try:
                services_data = json.loads(services_result.stdout)
                results['services'] = services_data
            except json.JSONDecodeError:
                logger.error("Failed to parse kubectl services output")
        
        return results
    
    def get_aws_status(self) -> Dict[str, Any]:
        """Get AWS infrastructure status"""
        results = {}
        
        if not settings.AWS_PROFILE:
            return results
        
        # Get EC2 instances
        ec2_result = self.execute_command(f"aws ec2 describe-instances --profile {settings.AWS_PROFILE} --output json")
        if ec2_result.success:
            try:
                ec2_data = json.loads(ec2_result.stdout)
                results['ec2_instances'] = ec2_data
                
                # Check for stopped instances
                stopped_instances = []
                for reservation in ec2_data.get('Reservations', []):
                    for instance in reservation.get('Instances', []):
                        if instance.get('State', {}).get('Name') != 'running':
                            stopped_instances.append({
                                'instance_id': instance.get('InstanceId'),
                                'state': instance.get('State', {}).get('Name'),
                                'instance_type': instance.get('InstanceType')
                            })
                
                results['stopped_instances'] = stopped_instances
                
            except json.JSONDecodeError:
                logger.error("Failed to parse AWS EC2 output")
        
        return results
    
    def get_gcp_status(self) -> Dict[str, Any]:
        """Get GCP infrastructure status"""
        results = {}
        
        if not settings.GCP_PROJECT:
            return results
        
        # Get Compute Engine instances
        gce_result = self.execute_command(
            f"gcloud compute instances list --project={settings.GCP_PROJECT} --format=json"
        )
        if gce_result.success:
            try:
                gce_data = json.loads(gce_result.stdout)
                results['gce_instances'] = gce_data
                
                # Check for stopped instances
                stopped_instances = []
                for instance in gce_data:
                    if instance.get('status') != 'RUNNING':
                        stopped_instances.append({
                            'name': instance.get('name'),
                            'status': instance.get('status'),
                            'zone': instance.get('zone')
                        })
                
                results['stopped_instances'] = stopped_instances
                
            except json.JSONDecodeError:
                logger.error("Failed to parse GCP instances output")
        
        return results
    
    def get_azure_status(self) -> Dict[str, Any]:
        """Get Azure infrastructure status"""
        results = {}
        
        if not settings.AZURE_SUBSCRIPTION:
            return results
        
        # Get Virtual Machines
        vm_result = self.execute_command(
            f"az vm list --subscription {settings.AZURE_SUBSCRIPTION} --output json"
        )
        if vm_result.success:
            try:
                vm_data = json.loads(vm_result.stdout)
                results['virtual_machines'] = vm_data
                
                # Check for stopped VMs
                stopped_vms = []
                for vm in vm_data:
                    # Get VM status
                    vm_status_result = self.execute_command(
                        f"az vm get-instance-view --resource-group {vm.get('resourceGroup')} --name {vm.get('name')} --output json"
                    )
                    if vm_status_result.success:
                        try:
                            status_data = json.loads(vm_status_result.stdout)
                            statuses = status_data.get('statuses', [])
                            power_state = next((s.get('displayStatus') for s in statuses if 'PowerState' in s.get('code', '')), 'Unknown')
                            
                            if power_state != 'VM running':
                                stopped_vms.append({
                                    'name': vm.get('name'),
                                    'resource_group': vm.get('resourceGroup'),
                                    'power_state': power_state
                                })
                        except json.JSONDecodeError:
                            logger.error(f"Failed to parse Azure VM status for {vm.get('name')}")
                
                results['stopped_vms'] = stopped_vms
                
            except json.JSONDecodeError:
                logger.error("Failed to parse Azure VMs output")
        
        return results