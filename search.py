"""
Search module for semantic and hybrid search
"""
from sqlalchemy import func, and_, or_, cast, String
from sqlalchemy.dialects.postgresql import JSONB
from models import Memory
from ai_engine import AIEngine
from database import get_db_session
from config import Config
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
                similarity_expr = (1 - Memory.embedding.cosine_distance(query_embedding))
                similarity = similarity_expr.label('similarity')
                base_query = session.query(
                    Memory,
                    similarity
                ).filter(
                    Memory.user_id == user_id
                )
                
                # Apply metadata filters if provided
                if filters:
                    for key, value in filters.items():
                        if value is not None:
                            if key == 'content_type':
                                base_query = base_query.filter(
                                    Memory.content_type == str(value)
                                )
                            else:
                                # Use JSONB operators for filtering
                                base_query = base_query.filter(
                                    Memory.meta[key].astext == str(value)
                                )
                
                # Apply minimum similarity threshold (optional)
                min_similarity = getattr(Config, 'SEMANTIC_MIN_SIMILARITY', 0.2)
                filtered_query = base_query
                if min_similarity is not None and min_similarity > 0:
                    filtered_query = base_query.filter(similarity_expr >= min_similarity)

                # Order by similarity and apply pagination
                results = filtered_query.order_by(
                    similarity_expr.desc()
                ).limit(limit).offset(offset).all()

                # Fallback: if threshold filtered everything, return best matches
                if not results and filtered_query is not base_query:
                    results = base_query.order_by(
                        similarity_expr.desc()
                    ).limit(limit).offset(offset).all()
                
                # Convert to dictionaries and add similarity score
                memories = []
                for memory, similarity in results:
                    memory_dict = memory.to_dict()
                    memory_dict['similarity'] = float(similarity)
                    memories.append(memory_dict)

                # Hybrid ranking: boost exact text/tag matches above pure semantic
                query_text = (query or '').strip().lower()
                if query_text:
                    for memory in memories:
                        display_text = (memory.get('display_text') or '').lower()
                        search_text = (memory.get('search_text') or '').lower()
                        tags = memory.get('metadata', {}).get('tags') or []
                        tags_text = " ".join(str(tag) for tag in tags).lower()

                        text_match = (
                            query_text in display_text
                            or query_text in search_text
                            or (tags_text and query_text in tags_text)
                        )
                        memory['_text_match'] = 1 if text_match else 0

                    memories.sort(
                        key=lambda m: (m.get('_text_match', 0), m.get('similarity', 0.0)),
                        reverse=True
                    )

                    for memory in memories:
                        memory.pop('_text_match', None)
                
                logger.info(
                    f"Search completed for user {user_id}: "
                    f"query='{query}', results={len(memories)}, "
                    f"min_similarity={min_similarity}, filters={filters}"
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
                            Memory.meta[key].astext == str(value)
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
                    Memory.meta['category'].astext,
                    func.count(Memory.id)
                ).filter(
                    Memory.user_id == user_id,
                    Memory.meta['category'].astext.isnot(None)
                ).group_by(
                    Memory.meta['category'].astext
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
