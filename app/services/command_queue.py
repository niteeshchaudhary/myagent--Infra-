"""Command queue system for tracking command execution order and status"""

import logging
import uuid
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

from config.settings import settings
from app.services.queue_broker import create_queue_broker, QueueBroker
from app.services.queue_persistence import QueuePersistence

logger = logging.getLogger(__name__)

class CommandStatus(Enum):
    """Status of a command in the queue"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"

@dataclass
class QueuedCommand:
    """Represents a command in the queue"""
    command: str
    round_number: int
    status: CommandStatus = CommandStatus.PENDING
    result: Optional[Any] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    queued_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'command': self.command,
            'round_number': self.round_number,
            'status': self.status.value,
            'error_message': self.error_message,
            'execution_time_ms': self.execution_time_ms,
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'result_exit_code': self.result.exit_code if self.result else None,
            'result_success': self.result.success if self.result else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedCommand':
        """Create QueuedCommand from dictionary"""
        cmd = cls(
            command=data['command'],
            round_number=data['round_number'],
            status=CommandStatus(data.get('status', 'pending')),
            error_message=data.get('error_message'),
            execution_time_ms=data.get('execution_time_ms'),
        )
        if data.get('queued_at'):
            cmd.queued_at = datetime.fromisoformat(data['queued_at'])
        if data.get('executed_at'):
            cmd.executed_at = datetime.fromisoformat(data['executed_at'])
        return cmd

class CommandQueue:
    """Queue system for tracking command execution order with broker support"""
    
    def __init__(self, broker: Optional[QueueBroker] = None, 
                 enable_persistence: Optional[bool] = None):
        # Initialize broker
        if broker is None:
            broker_kwargs = {}
            if settings.QUEUE_BROKER_TYPE == "redis":
                broker_kwargs = {
                    'host': settings.REDIS_HOST,
                    'port': settings.REDIS_PORT,
                    'db': settings.REDIS_DB,
                    'password': settings.REDIS_PASSWORD,
                    'queue_name': settings.QUEUE_NAME
                }
            elif settings.QUEUE_BROKER_TYPE == "celery":
                broker_kwargs = {
                    'broker_url': settings.QUEUE_BROKER_URL or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                    'queue_name': settings.QUEUE_NAME
                }
            elif settings.QUEUE_BROKER_TYPE == "rabbitmq":
                broker_kwargs = {
                    'host': settings.RABBITMQ_HOST,
                    'port': settings.RABBITMQ_PORT,
                    'username': settings.RABBITMQ_USERNAME,
                    'password': settings.RABBITMQ_PASSWORD,
                    'queue_name': settings.QUEUE_NAME
                }
            elif settings.QUEUE_BROKER_TYPE == "kafka":
                broker_kwargs = {
                    'bootstrap_servers': settings.KAFKA_BOOTSTRAP_SERVERS,
                    'topic': settings.QUEUE_NAME,
                    'group_id': settings.KAFKA_GROUP_ID
                }
            
            self.broker = create_queue_broker(settings.QUEUE_BROKER_TYPE, **broker_kwargs)
        else:
            self.broker = broker
        
        # Initialize persistence
        self.enable_persistence = enable_persistence if enable_persistence is not None else settings.QUEUE_PERSISTENCE_ENABLED
        if self.enable_persistence:
            self.persistence = QueuePersistence(settings.QUEUE_PERSISTENCE_PATH)
        else:
            self.persistence = None
        
        # Internal state (for tracking and compatibility)
        self.queue: List[QueuedCommand] = []
        self.executed_commands: List[QueuedCommand] = []
        self.current_round = 0
        
        # Task ID mapping for broker-based queues
        self._task_id_to_command: Dict[str, QueuedCommand] = {}
        
        # Load persisted state if available
        if self.persistence:
            self._load_persisted_state()
        
        logger.info(f"Initialized CommandQueue with broker: {settings.QUEUE_BROKER_TYPE}")
    
    def add_command(self, command: str, round_number: int) -> QueuedCommand:
        """Add a command to the queue"""
        queued_cmd = QueuedCommand(
            command=command,
            round_number=round_number
        )
        
        # Add to internal queue
        self.queue.append(queued_cmd)
        
        # Enqueue to broker
        task_id = str(uuid.uuid4())
        self._task_id_to_command[task_id] = queued_cmd
        
        task_data = {
            'task_id': task_id,
            'command': command,
            'round_number': round_number,
            'queued_at': queued_cmd.queued_at.isoformat()
        }
        
        if self.broker and self.broker.is_available():
            self.broker.enqueue(task_id, task_data)
        
        # Persist state
        self._persist_state()
        
        logger.debug(f"Added command to queue (round {round_number}): {command}")
        return queued_cmd
    
    def mark_executing(self, queued_cmd: QueuedCommand):
        """Mark a command as currently executing"""
        queued_cmd.status = CommandStatus.EXECUTING
        queued_cmd.executed_at = datetime.now()
        self._persist_state()
    
    def mark_completed(self, queued_cmd: QueuedCommand, result: Any):
        """Mark a command as completed with result"""
        queued_cmd.status = CommandStatus.COMPLETED
        queued_cmd.result = result
        queued_cmd.execution_time_ms = result.duration_ms if hasattr(result, 'duration_ms') else None
        
        # Move to executed list
        if queued_cmd in self.queue:
            self.queue.remove(queued_cmd)
        self.executed_commands.append(queued_cmd)
        
        # Remove from task mapping
        task_ids_to_remove = [tid for tid, cmd in self._task_id_to_command.items() if cmd == queued_cmd]
        for tid in task_ids_to_remove:
            del self._task_id_to_command[tid]
        
        self._persist_state()
        
        logger.debug(f"Command completed: {queued_cmd.command} (exit_code: {result.exit_code if hasattr(result, 'exit_code') else 'N/A'})")
    
    def mark_failed(self, queued_cmd: QueuedCommand, result: Any, error_message: Optional[str] = None):
        """Mark a command as failed"""
        queued_cmd.status = CommandStatus.FAILED
        queued_cmd.result = result
        queued_cmd.error_message = error_message or (result.stderr if hasattr(result, 'stderr') else "Unknown error")
        queued_cmd.execution_time_ms = result.duration_ms if hasattr(result, 'duration_ms') else None
        
        # Move to executed list
        if queued_cmd in self.queue:
            self.queue.remove(queued_cmd)
        self.executed_commands.append(queued_cmd)
        
        # Remove from task mapping
        task_ids_to_remove = [tid for tid, cmd in self._task_id_to_command.items() if cmd == queued_cmd]
        for tid in task_ids_to_remove:
            del self._task_id_to_command[tid]
        
        self._persist_state()
        
        logger.warning(f"Command failed: {queued_cmd.command} - {queued_cmd.error_message}")
    
    def mark_timeout(self, queued_cmd: QueuedCommand, result: Any):
        """Mark a command as timed out"""
        queued_cmd.status = CommandStatus.TIMEOUT
        queued_cmd.result = result
        queued_cmd.error_message = result.stderr if hasattr(result, 'stderr') else "Command timed out"
        queued_cmd.execution_time_ms = result.duration_ms if hasattr(result, 'duration_ms') else None
        
        # Move to executed list
        if queued_cmd in self.queue:
            self.queue.remove(queued_cmd)
        self.executed_commands.append(queued_cmd)
        
        # Remove from task mapping
        task_ids_to_remove = [tid for tid, cmd in self._task_id_to_command.items() if cmd == queued_cmd]
        for tid in task_ids_to_remove:
            del self._task_id_to_command[tid]
        
        self._persist_state()
        
        logger.warning(f"Command timed out: {queued_cmd.command}")
    
    def get_pending_commands(self, round_number: Optional[int] = None) -> List[QueuedCommand]:
        """Get pending commands, optionally filtered by round number"""
        if round_number is not None:
            return [cmd for cmd in self.queue if cmd.round_number == round_number and cmd.status == CommandStatus.PENDING]
        return [cmd for cmd in self.queue if cmd.status == CommandStatus.PENDING]
    
    def get_executed_commands(self, round_number: Optional[int] = None) -> List[QueuedCommand]:
        """Get executed commands, optionally filtered by round number"""
        if round_number is not None:
            return [cmd for cmd in self.executed_commands if cmd.round_number == round_number]
        return self.executed_commands.copy()
    
    def get_round_summary(self, round_number: int) -> Dict[str, Any]:
        """Get summary of commands for a specific round"""
        round_commands = [cmd for cmd in self.executed_commands if cmd.round_number == round_number]
        return {
            'round_number': round_number,
            'total_commands': len(round_commands),
            'completed': len([c for c in round_commands if c.status == CommandStatus.COMPLETED]),
            'failed': len([c for c in round_commands if c.status == CommandStatus.FAILED]),
            'timeout': len([c for c in round_commands if c.status == CommandStatus.TIMEOUT]),
            'commands': [c.to_dict() for c in round_commands]
        }
    
    def get_all_summary(self) -> Dict[str, Any]:
        """Get summary of all commands"""
        return {
            'total_queued': len(self.queue),
            'total_executed': len(self.executed_commands),
            'completed': len([c for c in self.executed_commands if c.status == CommandStatus.COMPLETED]),
            'failed': len([c for c in self.executed_commands if c.status == CommandStatus.FAILED]),
            'timeout': len([c for c in self.executed_commands if c.status == CommandStatus.TIMEOUT]),
            'rounds': list(set(cmd.round_number for cmd in self.executed_commands))
        }
    
    def clear(self):
        """Clear the queue"""
        self.queue.clear()
        self.executed_commands.clear()
        self.current_round = 0
        self._task_id_to_command.clear()
        
        # Clear broker queue
        if self.broker and self.broker.is_available():
            self.broker.clear()
        
        # Clear persisted state
        if self.persistence:
            self.persistence.clear_state()
        
        logger.info("Cleared command queue")
    
    def _persist_state(self):
        """Persist current queue state"""
        if not self.persistence:
            return
        
        pending_data = [cmd.to_dict() for cmd in self.queue]
        executed_data = [cmd.to_dict() for cmd in self.executed_commands]
        
        self.persistence.save_state(pending_data, executed_data, self.current_round)
    
    def _load_persisted_state(self):
        """Load persisted queue state"""
        if not self.persistence:
            return
        
        state = self.persistence.load_state()
        if not state:
            return
        
        try:
            # Restore pending commands
            for cmd_data in state.get('pending_commands', []):
                try:
                    cmd = QueuedCommand.from_dict(cmd_data)
                    self.queue.append(cmd)
                except Exception as e:
                    logger.warning(f"Failed to restore command from state: {e}")
            
            # Restore executed commands
            for cmd_data in state.get('executed_commands', []):
                try:
                    cmd = QueuedCommand.from_dict(cmd_data)
                    self.executed_commands.append(cmd)
                except Exception as e:
                    logger.warning(f"Failed to restore executed command from state: {e}")
            
            # Restore current round
            self.current_round = state.get('current_round', 0)
            
            logger.info(f"Restored {len(self.queue)} pending and {len(self.executed_commands)} executed commands from persistence")
        except Exception as e:
            logger.error(f"Failed to load persisted state: {e}")
    
    def get_broker_status(self) -> Dict[str, Any]:
        """Get status of the queue broker"""
        if not self.broker:
            return {'type': 'none', 'available': False}
        
        return {
            'type': settings.QUEUE_BROKER_TYPE,
            'available': self.broker.is_available(),
            'pending_count': self.broker.get_pending_count() if self.broker.is_available() else 0
        }

