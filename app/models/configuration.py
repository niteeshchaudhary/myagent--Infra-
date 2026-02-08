"""Configuration model for storing system settings"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float
from sqlalchemy.sql import func
from datetime import datetime

from . import Base

class Configuration(Base):
    """Configuration model for system settings"""
    
    __tablename__ = 'configurations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text)
    description = Column(Text)
    
    # Data type information
    value_type = Column(String(20), default='string')  # string, integer, float, boolean, json
    is_encrypted = Column(Boolean, default=False)
    is_required = Column(Boolean, default=False)
    
    # Validation
    validation_regex = Column(String(500))
    min_value = Column(Float)
    max_value = Column(Float)
    allowed_values = Column(Text)  # JSON array of allowed values
    
    # Categorization
    category = Column(String(50), default='general')  # general, database, llm, monitoring, etc.
    subcategory = Column(String(50))
    
    # Metadata
    created_by = Column(String(100))
    updated_by = Column(String(100))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<Configuration(key='{self.key}', value_type='{self.value_type}')>"
    
    def to_dict(self):
        """Convert configuration to dictionary"""
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'value_type': self.value_type,
            'is_encrypted': self.is_encrypted,
            'is_required': self.is_required,
            'validation_regex': self.validation_regex,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'allowed_values': self.allowed_values,
            'category': self.category,
            'subcategory': self.subcategory,
            'created_by': self.created_by,
            'updated_by': self.updated_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_typed_value(self):
        """Get value converted to appropriate type"""
        if not self.value:
            return None
            
        if self.value_type == 'integer':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'boolean':
            return self.value.lower() in ('true', '1', 'yes', 'on')
        elif self.value_type == 'json':
            import json
            return json.loads(self.value)
        else:  # string
            return self.value