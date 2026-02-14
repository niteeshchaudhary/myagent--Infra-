"""Service for finding similar incidents using embeddings"""

import logging
import numpy as np
from typing import List, Dict, Optional, Tuple
import json
from pathlib import Path

from config.settings import settings
from app.database.database import db_service
from app.models.incident import Incident

logger = logging.getLogger(__name__)


class SimilarityService:
    """Service for finding similar incidents using semantic embeddings"""
    
    def __init__(self):
        self.embedding_model = settings.EMBEDDING_MODEL
        self.vector_db_path = Path(settings.VECTOR_DB_PATH)
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize embedding provider
        self.embedder = None
        self.embedding_provider = self._detect_embedding_provider()
        self._initialize_embedder()
    
    def _detect_embedding_provider(self) -> str:
        """Detect which embedding provider to use based on configuration"""
        # If OpenAI is configured and LLM provider is OpenAI, use OpenAI embeddings
        if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
            return "openai"
        # Otherwise use local sentence-transformers
        return "sentence-transformers"
    
    def _initialize_embedder(self):
        """Initialize the embedding model"""
        try:
            if self.embedding_provider == "openai":
                if not settings.OPENAI_API_KEY:
                    logger.warning("OpenAI API key not found, falling back to sentence-transformers")
                    self.embedding_provider = "sentence-transformers"
                    self._initialize_embedder()
                    return
                
                import openai
                self.embedder = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("OpenAI embeddings initialized")
                
            elif self.embedding_provider == "sentence-transformers":
                from sentence_transformers import SentenceTransformer
                self.embedder = SentenceTransformer(self.embedding_model)
                logger.info(f"Sentence-Transformers model initialized: {self.embedding_model}")
                
        except ImportError as e:
            logger.error(f"Failed to import embedding library: {str(e)}")
            self.embedder = None
        except Exception as e:
            logger.error(f"Failed to initialize embedder: {str(e)}")
            self.embedder = None
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """
        Get embedding vector for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        if not self.embedder:
            logger.error("Embedder not initialized")
            return None
        
        try:
            if self.embedding_provider == "openai":
                response = self.embedder.embeddings.create(
                    model="text-embedding-ada-002",
                    input=text
                )
                return response.data[0].embedding
                
            elif self.embedding_provider == "sentence-transformers":
                embedding = self.embedder.encode(text)
                return embedding.tolist()
                
        except Exception as e:
            logger.error(f"Failed to get embedding: {str(e)}")
            return None
    
    def find_similar_incidents(
        self,
        query_text: str,
        top_k: int = 5,
        min_similarity: float = 0.5,
        exclude_resolved: bool = False
    ) -> List[Dict]:
        """
        Find similar incidents based on query text.
        
        Args:
            query_text: Text to search for (incident description/title)
            top_k: Number of similar incidents to return
            min_similarity: Minimum similarity threshold (0-1)
            exclude_resolved: Whether to exclude resolved incidents
            
        Returns:
            List of dicts with incident info and similarity score
        """
        try:
            # Get query embedding
            query_embedding = self.get_embedding(query_text)
            if query_embedding is None:
                logger.error("Failed to get query embedding")
                return []
            
            # Get all incidents from database
            with db_service.get_session() as session:
                query = session.query(Incident)
                
                if exclude_resolved:
                    from app.models.incident import IncidentStatus
                    query = query.filter(Incident.status != IncidentStatus.RESOLVED)
                
                incidents = query.all()
                
                if not incidents:
                    return []
                
                # Calculate similarities
                similarities = []
                for incident in incidents:
                    # Create text representation of incident
                    incident_text = f"{incident.title} {incident.description or ''} {incident.error_message or ''}"
                    
                    # Get incident embedding
                    incident_embedding = self.get_embedding(incident_text)
                    if incident_embedding is None:
                        continue
                    
                    # Calculate cosine similarity
                    similarity = self._cosine_similarity(query_embedding, incident_embedding)
                    
                    if similarity >= min_similarity:
                        similarities.append({
                            'incident_id': incident.id,
                            'title': incident.title,
                            'description': incident.description,
                            'severity': incident.severity.value if incident.severity else 'unknown',
                            'status': incident.status.value if incident.status else 'unknown',
                            'source_system': incident.source_system,
                            'affected_service': incident.affected_service,
                            'created_at': incident.created_at.isoformat() if incident.created_at else None,
                            'auto_fix_successful': incident.auto_fix_successful,
                            'similarity_score': float(similarity),
                            'error_message': incident.error_message[:200] if incident.error_message else None
                        })
                
                # Sort by similarity (highest first)
                similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
                
                # Return top k
                return similarities[:top_k]
                
        except Exception as e:
            logger.error(f"Error finding similar incidents: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            vec1 = np.array(vec1)
            vec2 = np.array(vec2)
            
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
            
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {str(e)}")
            return 0.0
    
    def is_available(self) -> bool:
        """Check if similarity service is available"""
        return self.embedder is not None
    
    def get_service_info(self) -> Dict:
        """Get information about the similarity service"""
        return {
            'provider': self.embedding_provider,
            'model': self.embedding_model,
            'available': self.is_available()
        }


# Global instance
similarity_service = SimilarityService()
