"""Service for managing SOP documents, including auto-generated ones"""

import json
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import re

from config.settings import settings
from app.database.database import db_service
from app.models.sop_document import SOPDocument

logger = logging.getLogger(__name__)


class SOPService:
    """Service for managing SOP documents"""
    
    def __init__(self):
        self.sop_path = Path(settings.SOP_DOCS_PATH)
        self.sop_path.mkdir(parents=True, exist_ok=True)
    
    def find_matching_sop(self, incident_title: str, incident_description: str, 
                         source_system: Optional[str] = None) -> Optional[SOPDocument]:
        """
        Find a matching SOP document for an incident.
        Searches by title similarity and keywords.
        
        Returns:
            Matching SOPDocument if found, None otherwise
        """
        try:
            with db_service.get_session() as session:
                # Get all published, non-deprecated SOPs
                sops = session.query(SOPDocument).filter(
                    SOPDocument.is_published == True,
                    SOPDocument.is_deprecated == False
                ).all()
                
                if not sops:
                    return None
                
                # Extract keywords from incident
                incident_keywords = self._extract_keywords(incident_title + " " + (incident_description or ""))
                
                best_match = None
                best_score = 0.0
                
                for sop in sops:
                    score = self._calculate_similarity_score(
                        incident_title,
                        incident_description,
                        incident_keywords,
                        sop.title,
                        sop.content,
                        source_system,
                        sop.category
                    )
                    
                    if score > best_score:
                        best_score = score
                        best_match = sop
                
                # Only return if similarity is above threshold (0.3 = 30%)
                if best_match and best_score >= 0.3:
                    logger.info(f"Found matching SOP: {best_match.title} (score: {best_score:.2f})")
                    return best_match
                
                return None
                
        except Exception as e:
            logger.error(f"Error finding matching SOP: {str(e)}")
            return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        if not text:
            return []
        
        # Simple keyword extraction - split and filter
        words = re.findall(r'\b\w+\b', text.lower())
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'}
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]
        return list(set(keywords))  # Remove duplicates
    
    def _calculate_similarity_score(
        self,
        incident_title: str,
        incident_description: str,
        incident_keywords: List[str],
        sop_title: str,
        sop_content: str,
        source_system: Optional[str],
        sop_category: Optional[str]
    ) -> float:
        """Calculate similarity score between incident and SOP"""
        score = 0.0
        
        # Title similarity (40% weight)
        title_similarity = self._text_similarity(incident_title.lower(), sop_title.lower())
        score += title_similarity * 0.4
        
        # Keyword matching in content (30% weight)
        if incident_keywords:
            content_lower = sop_content.lower()
            matching_keywords = sum(1 for kw in incident_keywords if kw in content_lower)
            keyword_score = matching_keywords / max(len(incident_keywords), 1)
            score += keyword_score * 0.3
        
        # Description similarity (20% weight)
        if incident_description:
            desc_similarity = self._text_similarity(incident_description.lower(), sop_content.lower())
            score += desc_similarity * 0.2
        
        # Category/system match (10% weight)
        if source_system and sop_category:
            if source_system.lower() in sop_category.lower() or sop_category.lower() in source_system.lower():
                score += 0.1
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity using word overlap"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(re.findall(r'\b\w+\b', text1.lower()))
        words2 = set(re.findall(r'\b\w+\b', text2.lower()))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def create_auto_sop(
        self,
        incident_title: str,
        incident_description: str,
        resolution_notes: str,
        commands_executed: List[str],
        source_system: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[SOPDocument]:
        """
        Create an auto-generated SOP document from a successful auto-fix.
        
        Returns:
            Created SOPDocument or None if creation failed
        """
        try:
            # Generate filename with auto_ prefix
            safe_title = re.sub(r'[^\w\s-]', '', incident_title)
            safe_title = re.sub(r'[-\s]+', '-', safe_title)
            filename = f"auto_{safe_title.lower()[:50]}.md"
            file_path = self.sop_path / filename
            
            # Ensure unique filename
            counter = 1
            while file_path.exists():
                filename = f"auto_{safe_title.lower()[:50]}_{counter}.md"
                file_path = self.sop_path / filename
                counter += 1
            
            # Create SOP content
            sop_content = self._generate_sop_content(
                incident_title,
                incident_description,
                resolution_notes,
                commands_executed,
                source_system,
                error_message
            )
            
            # Write to file
            file_path.write_text(sop_content, encoding='utf-8')
            logger.info(f"Created auto SOP file: {file_path}")
            
            # Calculate file hash
            file_hash = self._calculate_file_hash(file_path)
            
            # Extract keywords
            keywords = self._extract_keywords(incident_title + " " + (incident_description or ""))
            
            # Create database entry
            with db_service.get_session() as session:
                sop_doc = SOPDocument(
                    title=f"Auto: {incident_title}",
                    content=sop_content,
                    category=source_system or "general",
                    file_path=str(file_path),
                    file_hash=file_hash,
                    version="1.0",
                    keywords=json.dumps(keywords),
                    summary=f"Auto-generated SOP for resolving: {incident_title}",
                    is_published=True,
                    is_deprecated=False,
                    created_by="auto_fix_service",
                    tags=json.dumps(["auto-generated", "auto-fix", source_system] if source_system else ["auto-generated", "auto-fix"])
                )
                session.add(sop_doc)
                session.commit()
                session.refresh(sop_doc)
                
                logger.info(f"Created auto SOP document in database: {sop_doc.id} - {sop_doc.title}")
                return sop_doc
                
        except Exception as e:
            logger.error(f"Error creating auto SOP: {str(e)}")
            return None
    
    def _generate_sop_content(
        self,
        incident_title: str,
        incident_description: str,
        resolution_notes: str,
        commands_executed: List[str],
        source_system: Optional[str],
        error_message: Optional[str]
    ) -> str:
        """Generate SOP content from incident resolution"""
        content_parts = [
            f"# {incident_title}",
            "",
            "## Overview",
            f"This SOP was auto-generated from a successful auto-fix resolution.",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Source System:** {source_system or 'Unknown'}",
            "",
            "## Problem Description",
            "",
            incident_description or "No description provided.",
            ""
        ]
        
        if error_message:
            content_parts.extend([
                "## Error Message",
                "",
                f"```",
                error_message,
                "```",
                ""
            ])
        
        content_parts.extend([
            "## Resolution Steps",
            "",
            "### Commands Executed",
            ""
        ])
        
        for i, cmd in enumerate(commands_executed, 1):
            content_parts.append(f"{i}. `{cmd}`")
        
        content_parts.extend([
            "",
            "### Resolution Notes",
            "",
            resolution_notes,
            "",
            "## Notes",
            "",
            "- This SOP was automatically generated by the auto-fix service.",
            "- Review and validate the solution before using in production.",
            "- Update this SOP if the resolution process changes.",
            ""
        ])
        
        return "\n".join(content_parts)
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file"""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            return file_hash
        except Exception as e:
            logger.error(f"Error calculating file hash: {str(e)}")
            return ""
    
    def get_sop_commands(self, sop: SOPDocument) -> List[str]:
        """
        Extract commands from SOP content.
        Looks for code blocks and command patterns.
        """
        commands = []
        
        if not sop.content:
            return commands
        
        # Look for code blocks with commands
        code_block_pattern = r'```(?:bash|sh|shell)?\n(.*?)```'
        matches = re.findall(code_block_pattern, sop.content, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            lines = match.strip().split('\n')
            for line in lines:
                line = line.strip()
                # Skip comments and empty lines
                if line and not line.startswith('#'):
                    # Extract command (remove numbering like "1. kubectl get pods")
                    cmd = re.sub(r'^\d+\.\s*', '', line)
                    if cmd:
                        commands.append(cmd)
        
        # Also look for inline code commands
        inline_pattern = r'`([^`]+)`'
        inline_matches = re.findall(inline_pattern, sop.content)
        for match in inline_matches:
            if match.strip() and not match.startswith('#'):
                cmd = re.sub(r'^\d+\.\s*', '', match.strip())
                if cmd and cmd not in commands:
                    commands.append(cmd)
        
        return commands


# Global instance
sop_service = SOPService()

