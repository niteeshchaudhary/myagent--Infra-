"""Service for managing allowed and not-allowed command lists"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Literal
from config.settings import settings

logger = logging.getLogger(__name__)


class CommandListManager:
    """Manages allowed and not-allowed command lists with persistence"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or "data/command_lists.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()
    
    def _load_config(self):
        """Load command lists from file or use defaults from settings"""
        # Default not-allowed commands if not in settings
        default_not_allowed = [
            "kubectl delete",
            "kubectl apply",
            "kubectl create",
            "rm -rf",
            "format",
            "dd if="
        ]
        
        # Safely get settings with fallbacks
        default_allowed = getattr(settings, 'ALLOWED_COMMANDS', [])
        default_not_allowed_settings = getattr(settings, 'NOT_ALLOWED_COMMANDS', default_not_allowed)
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.allowed_commands = config.get('allowed_commands', default_allowed)
                    self.not_allowed_commands = config.get('not_allowed_commands', default_not_allowed_settings)
                logger.info(f"Loaded command lists from {self.config_path}")
            else:
                # Use defaults from settings
                self.allowed_commands = list(default_allowed) if default_allowed else []
                self.not_allowed_commands = list(default_not_allowed_settings) if default_not_allowed_settings else []
                self._save_config()  # Save defaults to file
                logger.info("Using default command lists from settings")
        except Exception as e:
            logger.error(f"Failed to load command lists: {e}")
            # Fallback to settings defaults
            self.allowed_commands = list(default_allowed) if default_allowed else []
            self.not_allowed_commands = list(default_not_allowed_settings) if default_not_allowed_settings else []
    
    def _save_config(self) -> bool:
        """Save command lists to file"""
        try:
            config = {
                'allowed_commands': self.allowed_commands,
                'not_allowed_commands': self.not_allowed_commands
            }
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved command lists to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save command lists: {e}")
            return False
    
    def get_allowed_commands(self) -> List[str]:
        """Get list of allowed commands"""
        return self.allowed_commands.copy()
    
    def get_not_allowed_commands(self) -> List[str]:
        """Get list of not-allowed commands"""
        return self.not_allowed_commands.copy()
    
    def set_allowed_commands(self, commands: List[str]) -> bool:
        """Update allowed commands list"""
        self.allowed_commands = [cmd.strip() for cmd in commands if cmd.strip()]
        return self._save_config()
    
    def set_not_allowed_commands(self, commands: List[str]) -> bool:
        """Update not-allowed commands list"""
        self.not_allowed_commands = [cmd.strip() for cmd in commands if cmd.strip()]
        return self._save_config()
    
    def add_allowed_command(self, command: str) -> bool:
        """Add a command to allowed list"""
        cmd = command.strip()
        if cmd and cmd not in self.allowed_commands:
            self.allowed_commands.append(cmd)
            return self._save_config()
        return False
    
    def remove_allowed_command(self, command: str) -> bool:
        """Remove a command from allowed list"""
        if command in self.allowed_commands:
            self.allowed_commands.remove(command)
            return self._save_config()
        return False
    
    def add_not_allowed_command(self, command: str) -> bool:
        """Add a command to not-allowed list"""
        cmd = command.strip()
        if cmd and cmd not in self.not_allowed_commands:
            self.not_allowed_commands.append(cmd)
            return self._save_config()
        return False
    
    def remove_not_allowed_command(self, command: str) -> bool:
        """Remove a command from not-allowed list"""
        if command in self.not_allowed_commands:
            self.not_allowed_commands.remove(command)
            return self._save_config()
        return False
    
    def _matches_pattern(self, command: str, pattern: str) -> bool:
        """
        Check if a command matches a pattern.
        Supports wildcard (*) at the end of pattern to match any suffix.
        
        Examples:
            - Pattern "kubectl get" matches "kubectl get pods"
            - Pattern "kubectl config use-context*" matches "kubectl config use-context kind-kind"
            - Pattern "kubectl config use-context*" matches "kubectl config use-context my-cluster"
        """
        cmd = command.strip()
        pattern = pattern.strip()
        
        # If pattern ends with *, treat it as a wildcard prefix match
        if pattern.endswith('*'):
            # Remove the * and check if command starts with the pattern
            prefix = pattern[:-1].strip()
            return cmd.startswith(prefix)
        else:
            # Regular prefix match (backward compatible)
            return cmd.startswith(pattern)
    
    def get_command_status(self, command: str) -> Literal["allowed", "blocked", "needs_approval"]:
        """
        Get the status of a command.
        Supports wildcard patterns (e.g., "kubectl config use-context*").
        
        Returns:
            "allowed": Command is in allowed list - execute directly
            "blocked": Command is in not-allowed list - reject without approval
            "needs_approval": Command is in neither list - require approval
        """
        cmd = command.strip()
        
        # First check not-allowed list (takes precedence - always blocked)
        for not_allowed in self.not_allowed_commands:
            if self._matches_pattern(cmd, not_allowed):
                return "blocked"
        
        # Then check allowed list
        for allowed in self.allowed_commands:
            if self._matches_pattern(cmd, allowed):
                return "allowed"
        
        # If not in either list, require approval
        return "needs_approval"
    
    def is_command_allowed(self, command: str) -> bool:
        """
        Check if a command is allowed (backward compatibility).
        Returns True only if status is "allowed", False otherwise.
        """
        return self.get_command_status(command) == "allowed"
    
    def is_command_blocked(self, command: str) -> bool:
        """Check if a command is explicitly blocked (in not-allowed list)"""
        return self.get_command_status(command) == "blocked"
    
    def needs_approval(self, command: str) -> bool:
        """Check if a command needs approval (not in either list)"""
        return self.get_command_status(command) == "needs_approval"
    
    def get_config_summary(self) -> Dict[str, any]:
        """Get summary of current configuration"""
        return {
            'allowed_count': len(self.allowed_commands),
            'not_allowed_count': len(self.not_allowed_commands),
            'config_path': str(self.config_path)
        }


# Global instance
command_list_manager = CommandListManager()

