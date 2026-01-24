"""SOP Document model for managing knowledge base documents"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class SOPDocument(Base):
    """SOP Document model for knowledge base management"""
    
    __tablename__ = 'sop_documents'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    
    # Categorization
    category = Column(String(100))  # kubernetes, aws, gcp, azure, general
    subcategory = Column(String(100))
    tags = Column(Text)  # JSON array of tags
    
    # Document metadata
    file_path = Column(String(500))  # Original file path
    file_hash = Column(String(64))   # SHA-256 hash for change detection
    version = Column(String(20), default='1.0')
    
    # Content analysis
    keywords = Column(Text)  # JSON array of extracted keywords
    summary = Column(Text)   # AI-generated summary
    
    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    effectiveness_score = Column(Float, default=0.0)  # Based on successful resolutions
    
    # Validation status
    is_validated = Column(Boolean, default=False)
    validated_by = Column(String(100))
    validated_at = Column(DateTime(timezone=True))
    
    # Publishing status
    is_published = Column(Boolean, default=True)
    is_deprecated = Column(Boolean, default=False)
    
    # Metadata
    created_by = Column(String(100))
    updated_by = Column(String(100))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<SOPDocument(id={self.id}, title='{self.title}', category='{self.category}')>"
    
    def to_dict(self):
        """Convert SOP document to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'category': self.category,
            'subcategory': self.subcategory,
            'tags': self.tags,
            'file_path': self.file_path,
            'file_hash': self.file_hash,
            'version': self.version,
            'keywords': self.keywords,
            'summary': self.summary,
            'usage_count': self.usage_count,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'effectiveness_score': self.effectiveness_score,
            'is_validated': self.is_validated,
            'validated_by': self.validated_by,
            'validated_at': self.validated_at.isoformat() if self.validated_at else None,
            'is_published': self.is_published,
            'is_deprecated': self.is_deprecated,
            'created_by': self.created_by,
            'updated_by': self.updated_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def increment_usage(self):
        """Increment usage count and update last used timestamp"""
        self.usage_count = (self.usage_count or 0) + 1
        self.last_used_at = datetime.utcnow()
    
    def update_effectiveness(self, success: bool):
        """Update effectiveness score based on resolution success"""
        current_score = self.effectiveness_score or 0.0
        usage_count = self.usage_count or 1
        
        # Simple moving average with more weight on recent results
        if success:
            self.effectiveness_score = (current_score * (usage_count - 1) + 1.0) / usage_count
        else:
            self.effectiveness_score = (current_score * (usage_count - 1) + 0.0) / usage_count