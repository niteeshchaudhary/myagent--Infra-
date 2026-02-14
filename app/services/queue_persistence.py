"""Persistence layer for queue state"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class QueuePersistence:
    """Handles persistence of queue state to disk"""
    
    def __init__(self, persistence_path: str = "data/queue_state.json"):
        self.persistence_path = Path(persistence_path)
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
    
    def save_state(self, pending_commands: List[Dict[str, Any]], 
                   executed_commands: List[Dict[str, Any]],
                   current_round: int) -> bool:
        """Save queue state to disk"""
        try:
            state = {
                'pending_commands': pending_commands,
                'executed_commands': executed_commands,
                'current_round': current_round,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.persistence_path, 'w') as f:
                json.dump(state, f, indent=2, default=str)
            
            logger.debug(f"Saved queue state to {self.persistence_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save queue state: {e}")
            return False
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load queue state from disk"""
        try:
            if not self.persistence_path.exists():
                logger.debug("No persisted queue state found")
                return None
            
            with open(self.persistence_path, 'r') as f:
                state = json.load(f)
            
            logger.info(f"Loaded queue state from {self.persistence_path}")
            return state
        except Exception as e:
            logger.error(f"Failed to load queue state: {e}")
            return None
    
    def clear_state(self) -> bool:
        """Clear persisted queue state"""
        try:
            if self.persistence_path.exists():
                self.persistence_path.unlink()
                logger.info("Cleared persisted queue state")
            return True
        except Exception as e:
            logger.error(f"Failed to clear queue state: {e}")
            return False
    
    def state_exists(self) -> bool:
        """Check if persisted state exists"""
        return self.persistence_path.exists()

