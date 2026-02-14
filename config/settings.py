"""
Configuration settings for the DevOps Agent
"""
from pydantic_settings import BaseSettings
from typing import Optional, List
import os
from pathlib import Path

class Settings(BaseSettings):
    """Main configuration settings"""
    
    # Application settings
    APP_NAME: str = "DevOps Monitoring Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database settings
    DATABASE_TYPE: str = "sqlite"  # sqlite or postgresql
    DATABASE_URL: Optional[str] = None
    SQLITE_DB_PATH: str = "data/devops_agent.db"
    
    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Queue Broker settings
    QUEUE_BROKER_TYPE: str = "internal"  # internal, redis, celery, rabbitmq, kafka
    QUEUE_BROKER_URL: Optional[str] = None  # For Celery: redis://localhost:6379/0
    QUEUE_NAME: str = "command_queue"
    
    # RabbitMQ settings
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USERNAME: str = "guest"
    RABBITMQ_PASSWORD: str = "guest"
    
    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_GROUP_ID: str = "devops_agent"
    
    # Queue persistence settings
    QUEUE_PERSISTENCE_ENABLED: bool = True
    QUEUE_PERSISTENCE_PATH: str = "data/queue_state.json"
    
    # LLM Configuration
    LLM_PROVIDER: str = "ollama"  # ollama, openai, groq
    OPENAI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OLLAMA_HOST: str = "http://localhost:11434"
    DEFAULT_MODEL: str = "llama2"
    
    # Monitoring settings
    POLLING_INTERVAL: int = 300  # seconds
    MAX_RETRIES: int = 3
    WEBHOOK_PORT: int = 8088
    WEBHOOK_SECRET: Optional[str] = None
    
    # Kubernetes settings
    KUBECONFIG_PATH: Optional[str] = None
    K8S_NAMESPACE: str = "default"
    
    # Cloud CLI settings
    AWS_PROFILE: Optional[str] = None
    GCP_PROJECT: Optional[str] = None
    AZURE_SUBSCRIPTION: Optional[str] = None
    
    # Approval system settings
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL: Optional[str] = None
    
    # Email settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    ALERT_EMAILS: List[str] = []
    
    # RAG settings
    VECTOR_DB_PATH: str = "data/vector_db"
    SOP_DOCS_PATH: str = "data/sops"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    
    # Security settings
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALLOWED_COMMANDS: List[str] = [
        "kubectl get pods",
        "kubectl get services",
        "kubectl get nodes",
        "kubectl config view",
        "kubectl cluster-info",
        "kubectl describe",
        "kubectl logs",
        "aws ec2 describe-instances",
        "gcloud compute instances list",
        "az vm list"
    ]
    NOT_ALLOWED_COMMANDS: List[str] = [
        "kubectl delete",
        "kubectl apply",
        "kubectl create",
        "rm -rf",
        "format",
        "dd if="
    ]
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/devops_agent.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()

# Ensure required directories exist
def ensure_directories():
    """Create necessary directories if they don't exist"""
    dirs = [
        Path(settings.SQLITE_DB_PATH).parent,
        Path(settings.VECTOR_DB_PATH),
        Path(settings.SOP_DOCS_PATH),
        Path(settings.LOG_FILE).parent
    ]
    
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

ensure_directories()