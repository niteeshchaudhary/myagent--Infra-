"""Notification service for sending messages to various channels"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from config.settings import settings

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for sending notifications to various channels"""
    
    def __init__(self):
        self.telegram_available = False
        self.slack_available = False
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize notification clients"""
        # Telegram
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            try:
                from telegram import Bot
                self.telegram_bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                self.telegram_chat_id = settings.TELEGRAM_CHAT_ID
                # Test connection
                self.telegram_bot.get_me()
                self.telegram_available = True
                logger.info("Telegram notification service initialized")
            except ImportError:
                logger.warning("python-telegram-bot not installed, Telegram notifications disabled")
                self.telegram_available = False
            except Exception as e:
                logger.warning(f"Failed to initialize Telegram: {e}")
                self.telegram_available = False
        
        # Slack
        if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL:
            try:
                from slack_sdk import WebClient
                self.slack_client = WebClient(token=settings.SLACK_BOT_TOKEN)
                self.slack_channel = settings.SLACK_CHANNEL
                self.slack_available = True
                logger.info("Slack notification service initialized")
            except ImportError:
                logger.warning("slack-sdk not installed, Slack notifications disabled")
            except Exception as e:
                logger.warning(f"Failed to initialize Slack: {e}")
    
    def send_approval_request(
        self,
        incident_id: int,
        incident_title: str,
        commands: List[str],
        reason: str = "Commands not in allowed list"
    ) -> Dict[str, Any]:
        """
        Send approval request for commands via all available channels
        
        Returns:
            dict with status of each channel: {'telegram': True/False, 'slack': True/False}
        """
        results = {}
        
        message = self._format_approval_message(incident_id, incident_title, commands, reason)
        
        # Send via Telegram
        if self.telegram_available:
            try:
                self.telegram_bot.send_message(
                    chat_id=self.telegram_chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                results['telegram'] = True
                logger.info(f"Sent approval request to Telegram for incident {incident_id}")
            except Exception as e:
                results['telegram'] = False
                logger.error(f"Failed to send Telegram notification: {e}")
        
        # Send via Slack
        if self.slack_available:
            try:
                self.slack_client.chat_postMessage(
                    channel=self.slack_channel,
                    text=message
                )
                results['slack'] = True
                logger.info(f"Sent approval request to Slack for incident {incident_id}")
            except Exception as e:
                results['slack'] = False
                logger.error(f"Failed to send Slack notification: {e}")
        
        return results
    
    def _format_approval_message(
        self,
        incident_id: int,
        incident_title: str,
        commands: List[str],
        reason: str
    ) -> str:
        """Format approval request message"""
        message = f"🔐 *APPROVAL REQUEST*\n\n"
        message += f"*Incident:* #{incident_id} - {incident_title}\n"
        message += f"*Reason:* {reason}\n\n"
        message += f"*Commands Requested:* ({len(commands)} command(s))\n"
        for i, cmd in enumerate(commands, 1):
            message += f"{i}. `{cmd}`\n"
        message += f"\n⚠️ These commands are not in the allowed list.\n"
        message += f"Please approve via the UI: http://localhost:8501\n"
        message += f"Or reply with 'APPROVE {incident_id}' to approve.\n"
        message += f"\n*Request Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return message
    
    def send_notification(self, message: str, title: Optional[str] = None) -> Dict[str, Any]:
        """Send a general notification"""
        results = {}
        full_message = f"{title}\n\n{message}" if title else message
        
        if self.telegram_available:
            try:
                self.telegram_bot.send_message(
                    chat_id=self.telegram_chat_id,
                    text=full_message
                )
                results['telegram'] = True
            except Exception as e:
                results['telegram'] = False
                logger.error(f"Failed to send Telegram notification: {e}")
        
        if self.slack_available:
            try:
                self.slack_client.chat_postMessage(
                    channel=self.slack_channel,
                    text=full_message
                )
                results['slack'] = True
            except Exception as e:
                results['slack'] = False
                logger.error(f"Failed to send Slack notification: {e}")
        
        return results

