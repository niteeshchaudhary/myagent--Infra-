"""Database service for handling connections and operations"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator
import logging

from config.settings import settings
from app.models import Base
from app.models.incident import Incident
from app.models.audit_log import AuditLog
from app.models.configuration import Configuration
from app.models.sop_document import SOPDocument

logger = logging.getLogger(__name__)

class DatabaseService:
    """Database service for managing connections and operations"""
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize database connection and create tables"""
        try:
            if settings.DATABASE_TYPE == "sqlite":
                database_url = f"sqlite:///{settings.SQLITE_DB_PATH}"
            elif settings.DATABASE_TYPE == "postgresql":
                if not settings.DATABASE_URL:
                    raise ValueError("DATABASE_URL is required for PostgreSQL")
                database_url = settings.DATABASE_URL
            else:
                raise ValueError(f"Unsupported database type: {settings.DATABASE_TYPE}")
            
            self.engine = create_engine(
                database_url,
                echo=settings.DEBUG,
                pool_pre_ping=True
            )
            
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            
            # Create all tables
            self._create_tables()
            
            logger.info(f"Database initialized successfully with {settings.DATABASE_TYPE}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    def _create_tables(self):
        """Create all database tables"""
        try:
            # Import all models to ensure they're registered with Base
            from app.models.incident import Incident
            from app.models.audit_log import AuditLog
            from app.models.configuration import Configuration
            from app.models.sop_document import SOPDocument
            
            # Create all tables using the shared Base metadata
            Base.metadata.create_all(bind=self.engine)
            
            logger.info("Database tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create database tables: {str(e)}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            session.close()
    
    def get_session_sync(self) -> Session:
        """Get database session for synchronous operations"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")
    
    def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False
    
    def reset_database(self):
        """Reset database by dropping and recreating all tables"""
        try:
            logger.warning("Resetting database - all data will be lost!")
            
            # Drop all tables using the shared Base metadata
            Base.metadata.drop_all(bind=self.engine)
            
            # Recreate all tables
            self._create_tables()
            
            logger.info("Database reset completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to reset database: {str(e)}")
            raise

# Global database instance
db_service = DatabaseService()

# Dependency for FastAPI/other frameworks
def get_database() -> DatabaseService:
    """Get database service instance"""
    return db_service

def get_db_session() -> Generator[Session, None, None]:
    """Get database session generator"""
    with db_service.get_session() as session:
        yield session