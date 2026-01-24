"""Main entry point for the DevOps Monitoring Agent"""

import os
import sys
import logging
import signal
import threading
import time
from typing import Optional
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from app.database.database import db_service
from app.monitoring.polling_monitor import PollingMonitor
from app.monitoring.webhook_monitor import WebhookMonitor
from app.models.audit_log import AuditLog, ActionType

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class DevOpsAgent:
    """Main DevOps Monitoring Agent application"""
    
    def __init__(self):
        self.polling_monitor: Optional[PollingMonitor] = None
        self.webhook_monitor: Optional[WebhookMonitor] = None
        self.is_running = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown()
        sys.exit(0)
    
    def startup_checks(self) -> bool:
        """Perform startup health checks"""
        logger.info("Performing startup checks...")
        
        try:
            # Check database connectivity
            if not db_service.health_check():
                logger.error("Database health check failed")
                return False
            logger.info("✓ Database connection healthy")
            
            # Ensure required directories exist
            from config.settings import ensure_directories
            ensure_directories()
            logger.info("✓ Required directories verified")
            
            # Check if required CLI tools are available
            self._check_cli_tools()
            
            # Log startup
            self._log_startup()
            
            logger.info("All startup checks passed")
            return True
            
        except Exception as e:
            logger.error(f"Startup checks failed: {str(e)}")
            return False
    
    def _check_cli_tools(self):
        """Check availability of CLI tools"""
        tools_to_check = []
        
        # Always check kubectl for Kubernetes
        tools_to_check.append(('kubectl', 'kubectl version --client'))
        
        # Check cloud tools if configured
        if settings.AWS_PROFILE:
            tools_to_check.append(('aws', 'aws --version'))
        
        if settings.GCP_PROJECT:
            tools_to_check.append(('gcloud', 'gcloud version'))
        
        if settings.AZURE_SUBSCRIPTION:
            tools_to_check.append(('az', 'az --version'))
        
        for tool_name, version_cmd in tools_to_check:
            try:
                import subprocess
                result = subprocess.run(
                    version_cmd.split(),
                    capture_output=True,
                    timeout=10
                )
                if result.returncode == 0:
                    logger.info(f"✓ {tool_name} CLI available")
                else:
                    logger.warning(f"⚠ {tool_name} CLI not available or not configured")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                logger.warning(f"⚠ {tool_name} CLI not found")
    
    def start_services(self):
        """Start all monitoring services"""
        logger.info("Starting DevOps Monitoring Agent services...")
        
        try:
            # Start polling monitor
            logger.info("Starting polling monitor...")
            self.polling_monitor = PollingMonitor()
            self.polling_monitor.start()
            logger.info("✓ Polling monitor started")
            
            # Start webhook monitor
            logger.info("Starting webhook monitor...")
            self.webhook_monitor = WebhookMonitor()
            self.webhook_monitor.start()
            logger.info(f"✓ Webhook monitor started on port {self.webhook_monitor.port}")
            
            self.is_running = True
            logger.info("🚀 All services started successfully!")
            
            # Log service startup
            self._log_service_start()
            
        except Exception as e:
            logger.error(f"Failed to start services: {str(e)}")
            self.shutdown()
            raise
    
    def shutdown(self):
        """Shutdown all services gracefully"""
        if not self.is_running:
            return
        
        logger.info("Shutting down DevOps Monitoring Agent...")
        
        try:
            # Stop polling monitor
            if self.polling_monitor:
                logger.info("Stopping polling monitor...")
                self.polling_monitor.stop()
                logger.info("✓ Polling monitor stopped")
            
            # Stop webhook monitor
            if self.webhook_monitor:
                logger.info("Stopping webhook monitor...")
                self.webhook_monitor.stop()
                logger.info("✓ Webhook monitor stopped")
            
            # Close database connections
            logger.info("Closing database connections...")
            db_service.close()
            logger.info("✓ Database connections closed")
            
            self.is_running = False
            
            # Log shutdown
            self._log_shutdown()
            
            logger.info("🛑 DevOps Monitoring Agent shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
    
    def run(self):
        """Run the main application"""
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
        
        # Perform startup checks
        if not self.startup_checks():
            logger.error("Startup checks failed, exiting")
            sys.exit(1)
        
        # Start services
        self.start_services()
        
        # Print status information
        self._print_status()
        
        # Keep the main thread alive
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.shutdown()
    
    def _print_status(self):
        """Print current status information"""
        print("\\n" + "="*60)
        print(f"🔧 {settings.APP_NAME} v{settings.APP_VERSION}")
        print("="*60)
        print(f"📊 Streamlit UI: Run 'streamlit run app/ui/main.py' in another terminal")
        print(f"📡 Polling Monitor: {'Running' if self.polling_monitor and self.polling_monitor.is_running else 'Stopped'}")
        print(f"🪝 Webhook Monitor: {'Running' if self.webhook_monitor and self.webhook_monitor.is_running else 'Stopped'}")
        
        if self.webhook_monitor:
            print(f"   Webhook Endpoints:")
            for endpoint in self.webhook_monitor.get_status().get('endpoints', []):
                print(f"   - {endpoint}")
        
        print(f"💾 Database: {settings.DATABASE_TYPE} ({'Healthy' if db_service.health_check() else 'Unhealthy'})")
        print(f"📁 Data Directory: {Path(settings.SQLITE_DB_PATH).parent}")
        print(f"📋 Log File: {settings.LOG_FILE}")
        print("="*60)
        print("Press Ctrl+C to stop")
        print("="*60 + "\\n")
    
    def _log_startup(self):
        """Log application startup"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=ActionType.MONITORING_CHECK,
                    action_description=f"DevOps Agent v{settings.APP_VERSION} started",
                    success=True,
                    user_id="system",
                    source_system="main"
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log startup: {str(e)}")
    
    def _log_service_start(self):
        """Log service startup"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=ActionType.MONITORING_CHECK,
                    action_description="All monitoring services started successfully",
                    success=True,
                    user_id="system",
                    source_system="main"
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log service start: {str(e)}")
    
    def _log_shutdown(self):
        """Log application shutdown"""
        try:
            with db_service.get_session() as session:
                audit_log = AuditLog(
                    action_type=ActionType.MONITORING_CHECK,
                    action_description="DevOps Agent shutdown completed",
                    success=True,
                    user_id="system",
                    source_system="main"
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to log shutdown: {str(e)}")

def main():
    """Main entry point"""
    try:
        agent = DevOpsAgent()
        agent.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()