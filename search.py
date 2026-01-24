"""
Search module for semantic and hybrid search
"""
from sqlalchemy import func, and_, or_, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from models import Memory
from ai_engine import AIEngine
from database import get_db_session
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class SearchEngine:
    """Hybrid search engine combining semantic and metadata search"""
    
    @staticmethod
    def search(
        user_id: int,
        query: str,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Perform hybrid search combining semantic similarity and metadata filtering
        
        Args:
            user_id: Telegram user ID
            query: Search query text
            limit: Maximum number of results
            offset: Pagination offset
            filters: Optional metadata filters (e.g., {'category': 'invoice'})
            
        Returns:
            List of memory dictionaries sorted by relevance
        """
        try:
            # Generate query embedding
            query_embedding = AIEngine.generate_query_embedding(query)
            
            with get_db_session() as session:
                # Build base query
                base_query = session.query(
                    Memory,
                    # Calculate cosine similarity (1 - cosine distance)
                    (1 - Memory.embedding.cosine_distance(query_embedding)).label('similarity')
                ).filter(
                    Memory.user_id == user_id
                )
                
                # Apply metadata filters if provided
                if filters:
                    for key, value in filters.items():
                        if value is not None:
                            # Use JSONB operators for filtering
                            base_query = base_query.filter(
                                Memory.metadata[key].astext == str(value)
                            )
                
                # Order by similarity and apply pagination
                results = base_query.order_by(
                    func.desc('similarity')
                ).limit(limit).offset(offset).all()
                
                # Convert to dictionaries and add similarity score
                memories = []
                for memory, similarity in results:
                    memory_dict = memory.to_dict()
                    memory_dict['similarity'] = float(similarity)
                    memories.append(memory_dict)
                
                logger.info(
                    f"Search completed for user {user_id}: "
                    f"query='{query}', results={len(memories)}"
                )
                
                return memories
                
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    @staticmethod
    def search_by_metadata(
        user_id: int,
        metadata_query: Dict,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict]:
        """
        Search by metadata fields only (no semantic search)
        
        Args:
            user_id: Telegram user ID
            metadata_query: Dictionary of metadata filters
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of memory dictionaries
        """
        try:
            with get_db_session() as session:
                query = session.query(Memory).filter(
                    Memory.user_id == user_id
                )
                
                # Apply metadata filters
                for key, value in metadata_query.items():
                    if value is not None:
                        query = query.filter(
                            Memory.metadata[key].astext == str(value)
                        )
                
                # Order by creation date (newest first)
                results = query.order_by(
                    Memory.created_at.desc()
                ).limit(limit).offset(offset).all()
                
                memories = [memory.to_dict() for memory in results]
                
                logger.info(
                    f"Metadata search completed for user {user_id}: "
                    f"filters={metadata_query}, results={len(memories)}"
                )
                
                return memories
                
        except Exception as e:
            logger.error(f"Metadata search failed: {e}")
            raise
    
    @staticmethod
    def get_recent_memories(
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        content_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Get recent memories for a user
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of results
            offset: Pagination offset
            content_type: Optional filter by content type
            
        Returns:
            List of memory dictionaries
        """
        try:
            with get_db_session() as session:
                query = session.query(Memory).filter(
                    Memory.user_id == user_id
                )
                
                if content_type:
                    query = query.filter(Memory.content_type == content_type)
                
                results = query.order_by(
                    Memory.created_at.desc()
                ).limit(limit).offset(offset).all()
                
                memories = [memory.to_dict() for memory in results]
                
                logger.info(
                    f"Retrieved {len(memories)} recent memories for user {user_id}"
                )
                
                return memories
                
        except Exception as e:
            logger.error(f"Failed to get recent memories: {e}")
            raise
    
    @staticmethod
    def get_memory_stats(user_id: int) -> Dict:
        """
        Get statistics about user's memories
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with statistics
        """
        try:
            with get_db_session() as session:
                # Total count
                total = session.query(func.count(Memory.id)).filter(
                    Memory.user_id == user_id
                ).scalar()
                
                # Count by type
                type_counts = session.query(
                    Memory.content_type,
                    func.count(Memory.id)
                ).filter(
                    Memory.user_id == user_id
                ).group_by(Memory.content_type).all()
                
                # Count by category (from metadata)
                category_counts = session.query(
                    Memory.metadata['category'].astext,
                    func.count(Memory.id)
                ).filter(
                    Memory.user_id == user_id,
                    Memory.metadata['category'].astext.isnot(None)
                ).group_by(
                    Memory.metadata['category'].astext
                ).limit(10).all()
                
                stats = {
                    'total_memories': total or 0,
                    'by_type': {ct: count for ct, count in type_counts},
                    'by_category': {cat: count for cat, count in category_counts if cat},
                }
                
                logger.info(f"Retrieved stats for user {user_id}")
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {'total_memories': 0, 'by_type': {}, 'by_category': {}}
