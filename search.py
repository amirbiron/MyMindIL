"""
Search module for semantic and hybrid search

Implements:
- Vector search using pgvector cosine distance
- Full-text search using PostgreSQL tsvector
- Hybrid search combining both using Reciprocal Rank Fusion (RRF)
"""
from sqlalchemy import func, and_, or_, cast, String, select, desc, case, literal, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from models import Memory
from ai_engine import AIEngine
from database import get_db_session
from config import Config
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SearchEngine:
    """Hybrid search engine combining semantic and metadata search"""

    @staticmethod
    def search(
        user_id: int,
        query: str,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict] = None,
        use_hybrid: bool = True
    ) -> List[Dict]:
        """
        Search memories using hybrid search (vector + keyword) with RRF fusion.
        
        Args:
            user_id: Telegram user ID
            query: Search query text
            limit: Maximum number of results
            offset: Pagination offset
            filters: Optional metadata filters
            use_hybrid: If True, use hybrid search; if False, use vector-only search
            
        Returns:
            List of memory dictionaries sorted by relevance
        """
        try:
            logger.info(f"Searching for query: '{query}' (hybrid={use_hybrid})")
            
            # Generate embedding for query
            try:
                query_embedding = AIEngine.generate_query_embedding(query)
            except ValueError as e:
                logger.error(f"Failed to generate embedding for query: {e}")
                return []

            with get_db_session() as session:
                if use_hybrid:
                    # Use hybrid search with RRF
                    return SearchEngine._hybrid_search(
                        session, user_id, query, query_embedding, 
                        limit, offset, filters
                    )
                else:
                    # Use vector-only search
                    return SearchEngine._vector_search(
                        session, user_id, query_embedding,
                        limit, offset, filters
                    )

        except Exception as e:
            logger.error(f"Search CRASHED: {e}", exc_info=True)
            return []

    @staticmethod
    def _vector_search(
        session,
        user_id: int,
        query_embedding: List[float],
        limit: int,
        offset: int,
        filters: Optional[Dict]
    ) -> List[Dict]:
        """
        Vector-only search using cosine distance.
        
        IMPORTANT: Uses ORDER BY distance ASC (not similarity DESC) to enable
        proper HNSW index usage. See: https://github.com/pgvector/pgvector
        """
        # Calculate distance (lower = more similar)
        distance_expr = Memory.embedding.cosine_distance(query_embedding)
        # Calculate similarity for display (higher = more similar)
        similarity_expr = (1 - distance_expr)
        
        # Build query
        stmt = session.query(Memory, similarity_expr.label('similarity')).filter(
            Memory.user_id == user_id,
            # מרחק בין וקטורים של מודלים שונים חסר משמעות (ראה Memory.embedding_model)
            Memory.embedding_model == AIEngine.EMBED_MODEL,
        )
        
        # Apply filters
        if filters:
            for key, value in filters.items():
                if value:
                    if key == 'content_type':
                        stmt = stmt.filter(Memory.content_type == str(value))
                    else:
                        stmt = stmt.filter(Memory.meta[key].astext == str(value))
        
        # Order by distance ASC (most similar first) - this allows HNSW index usage
        results = stmt.order_by(
            distance_expr.asc()
        ).limit(limit).offset(offset).all()
        
        memories = []
        logger.info(f"Vector search found {len(results)} results")
        
        for memory, similarity in results:
            final_score = float(similarity) if similarity is not None else 0.0
            logger.debug(f"ID: {memory.id} | Score: {final_score:.4f}")
            
            memory_dict = memory.to_dict()
            memory_dict['similarity'] = final_score
            memories.append(memory_dict)
        
        return memories

    @staticmethod
    def _apply_filters(query, filters: Optional[Dict]):
        """
        Apply metadata/content filters to a query.
        """
        if not filters:
            return query

        for key, value in filters.items():
            if value:
                if key == 'content_type':
                    query = query.filter(Memory.content_type == str(value))
                else:
                    query = query.filter(Memory.meta[key].astext == str(value))

        return query

    @staticmethod
    def _hybrid_search(
        session,
        user_id: int,
        query_text: str,
        query_embedding: List[float],
        limit: int,
        offset: int,
        filters: Optional[Dict],
        vec_candidates: int = 50,
        text_candidates: int = 50
    ) -> List[Dict]:
        """
        Fixed Hybrid Search: Uses OR logic for keywords to improve recall
        """
        # --- 1. מועמדים וקטורים (Vector Search) ---
        # שומרים על הלוגיקה הקיימת שלך שעובדת
        distance_expr = Memory.embedding.cosine_distance(query_embedding)
        
        vec_query = session.query(
            Memory.id.label("id"),
            (1 - distance_expr).label("vec_score")
        ).filter(
            Memory.user_id == user_id,
            # מרחק בין וקטורים של מודלים שונים חסר משמעות (ראה Memory.embedding_model).
            # שורות ממודל אחר עדיין נמצאות בחיפוש הטקסטואלי שלמטה.
            Memory.embedding_model == AIEngine.EMBED_MODEL,
        )
        
        vec_query = SearchEngine._apply_filters(vec_query, filters)
        vec_query = vec_query.order_by(distance_expr.asc()).limit(vec_candidates)
        
        # Dictionary: {id: score}
        vec_results = {str(row.id): float(row.vec_score or 0.0) for row in vec_query.all()}

        # --- 2. מועמדים טקסטואליים (Text Search) ---
        # התיקון הגדול: שימוש ב-OR (|) במקום ברירת המחדל
        
        # ניקוי בסיסי
        clean_query = query_text.replace("'", "").replace("&", "").replace("|", "")
        clean_words = clean_query.split()
        
        if clean_words:
            # מחבר את המילים עם OR ומחיל חיפוש גמיש
            # דוגמה: "אייקון נחש" הופך ל: "אייקון | נחש"
            ts_query_str = " | ".join(clean_words)
            tsq = func.to_tsquery('simple', ts_query_str)
        else:
            tsq = func.plainto_tsquery('simple', query_text)

        # שימוש ב-search_tsv הקיים
        # העמודה אינה במודל (נוצרת ב-ensure_search_infra), ולכן ניגשים אליה בשמה.
        # literal_column ולא text(): ב-SQLAlchemy 2.0 ל-TextClause אין .op(), והחיפוש
        # ההיברידי קרס על AttributeError בכל קריאה.
        search_tsv = literal_column("memories.search_tsv")
        text_rank = func.ts_rank_cd(search_tsv, tsq)
        
        text_query = session.query(
            Memory.id.label("id"),
            text_rank.label("text_score")
        ).filter(
            Memory.user_id == user_id,
            search_tsv.op("@@")(tsq)
        )
        
        text_query = SearchEngine._apply_filters(text_query, filters)
        text_query = text_query.order_by(text_rank.desc()).limit(text_candidates)
        
        text_results = {str(row.id): float(row.text_score or 0.0) for row in text_query.all()}

        # --- 3. מיזוג התוצאות (Simple Weighted Fusion) ---
        all_ids = set(vec_results.keys()) | set(text_results.keys())
        
        if not all_ids:
            return []

        scored_memories = []
        
        # שליפת האובייקטים המלאים
        memories_query = session.query(Memory).filter(Memory.id.in_(all_ids))
        memories_map = {str(m.id): m for m in memories_query.all()}

        for mid in all_ids:
            if mid not in memories_map:
                continue
                
            v_score = vec_results.get(mid, 0.0)
            t_score = text_results.get(mid, 0.0)
            
            # נוסחת השקלול:
            # הוקטור הוא הבסיס. אם יש התאמה בטקסט - זה בונוס שמקפיץ למעלה.
            # זה פותר את בעיית "קוד פייתון" (בונוס טקסט) מול "נחש" (בסיס וקטור)
            final_score = v_score + (t_score * 0.5)
            
            memory = memories_map[mid].to_dict()
            memory['similarity'] = final_score
            # שומרים גם את הציונים הנפרדים לדיבוג אם תרצה
            memory['debug_vec'] = v_score
            memory['debug_text'] = t_score
            
            scored_memories.append(memory)

        # מיון סופי לפי הציון המשוקלל
        scored_memories.sort(key=lambda x: x['similarity'], reverse=True)
        
        # החזרת הכמות המבוקשת (Pagination)
        return scored_memories[offset:offset+limit]

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
    def delete_memory(user_id: int, memory_id: str) -> bool:
        """
        Delete a specific memory for a user

        Args:
            user_id: Telegram user ID
            memory_id: Memory UUID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            with get_db_session() as session:
                # Find the memory - ensure it belongs to the user
                memory = session.query(Memory).filter(
                    Memory.id == memory_id,
                    Memory.user_id == user_id
                ).first()

                if not memory:
                    logger.warning(
                        f"Memory {memory_id} not found for user {user_id}"
                    )
                    return False

                session.delete(memory)
                logger.info(f"Deleted memory {memory_id} for user {user_id}")
                return True

        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

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
