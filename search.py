"""
Search module for semantic and hybrid search

Implements:
- Vector search using pgvector cosine distance
- Full-text search using PostgreSQL tsvector
- Hybrid search combining both using Reciprocal Rank Fusion (RRF)
"""
from sqlalchemy import func, and_, or_, cast, String, select, desc, case, text, literal
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
            Memory.user_id == user_id
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
    def _hybrid_search(
        session,
        user_id: int,
        query_text: str,
        query_embedding: List[float],
        limit: int,
        offset: int,
        filters: Optional[Dict],
        vec_candidates: int = 50,
        text_candidates: int = 50,
        rrf_k: int = 60,
        boost_code: float = 0.20,
        boost_text_type: float = 0.05
    ) -> List[Dict]:
        """
        Hybrid search combining vector similarity and full-text search using RRF.
        
        This approach helps fix issues like "recycling icon" ranking higher than
        "python code" when searching for "python code" - the keyword match on
        "python" will boost the code result even if the vector similarity is similar.
        
        Args:
            session: Database session
            user_id: User ID to filter by
            query_text: Original query text for keyword search
            query_embedding: Query embedding vector
            limit: Max results to return
            offset: Pagination offset
            filters: Optional metadata filters
            vec_candidates: Number of vector search candidates
            text_candidates: Number of text search candidates
            rrf_k: RRF smoothing constant (typically 30-100)
            boost_code: Score boost for content with code
            boost_text_type: Score boost for text content type
            
        Returns:
            List of memory dictionaries with hybrid scores
        """
        try:
            # ----- Vector candidates -----
            distance_expr = Memory.embedding.cosine_distance(query_embedding)
            
            vec_query = session.query(
                Memory.id.label("id"),
                func.rank().over(order_by=distance_expr.asc()).label("vec_rank"),
                (1 - distance_expr).label("vec_similarity")
            ).filter(Memory.user_id == user_id)
            
            # Apply filters to vector search
            if filters:
                for key, value in filters.items():
                    if value:
                        if key == 'content_type':
                            vec_query = vec_query.filter(Memory.content_type == str(value))
                        else:
                            vec_query = vec_query.filter(Memory.meta[key].astext == str(value))
            
            vec_query = vec_query.order_by(distance_expr.asc()).limit(vec_candidates)
            vec_results = {row.id: (row.vec_rank, row.vec_similarity) for row in vec_query.all()}
            
            # ----- Keyword candidates -----
            # Use plainto_tsquery with 'simple' config (works well for Hebrew + code)
            tsq = func.plainto_tsquery('simple', query_text)
            
            # Reference the search_tsv column (created by ensure_search_infra)
            search_tsv_col = text("memories.search_tsv")
            text_rank_expr = func.ts_rank_cd(search_tsv_col, tsq)
            
            text_query = session.query(
                Memory.id.label("id"),
                func.rank().over(order_by=text_rank_expr.desc()).label("text_rank"),
                text_rank_expr.label("text_score")
            ).filter(
                Memory.user_id == user_id,
                text(f"memories.search_tsv @@ plainto_tsquery('simple', :query)")
            ).params(query=query_text)
            
            # Apply same filters to text search
            if filters:
                for key, value in filters.items():
                    if value:
                        if key == 'content_type':
                            text_query = text_query.filter(Memory.content_type == str(value))
                        else:
                            text_query = text_query.filter(Memory.meta[key].astext == str(value))
            
            text_query = text_query.order_by(text_rank_expr.desc()).limit(text_candidates)
            text_results = {row.id: (row.text_rank, row.text_score) for row in text_query.all()}
            
            # ----- Combine candidates -----
            all_ids = set(vec_results.keys()) | set(text_results.keys())
            
            if not all_ids:
                logger.info("Hybrid search found no candidates")
                return []
            
            # Calculate RRF scores
            scored_ids = []
            for memory_id in all_ids:
                vec_rank, vec_sim = vec_results.get(memory_id, (None, 0))
                text_rank, text_score = text_results.get(memory_id, (None, 0))
                
                # RRF formula: 1 / (k + rank)
                rrf_score = 0.0
                if vec_rank is not None:
                    rrf_score += 1.0 / (rrf_k + vec_rank)
                if text_rank is not None:
                    rrf_score += 1.0 / (rrf_k + text_rank)
                
                scored_ids.append((memory_id, rrf_score, vec_sim or 0))
            
            # Sort by RRF score descending
            scored_ids.sort(key=lambda x: x[1], reverse=True)
            
            # Apply offset and limit
            scored_ids = scored_ids[offset:offset + limit]
            
            if not scored_ids:
                return []
            
            # Fetch full Memory objects
            memory_ids = [mid for mid, _, _ in scored_ids]
            memories_query = session.query(Memory).filter(Memory.id.in_(memory_ids))
            memories_map = {m.id: m for m in memories_query.all()}
            
            # Build results with boosts applied
            results = []
            for memory_id, rrf_score, vec_sim in scored_ids:
                memory = memories_map.get(memory_id)
                if not memory:
                    continue
                
                # Apply boosts
                final_score = rrf_score
                
                # Boost for code content
                if memory.meta and memory.meta.get("contains_code"):
                    final_score += boost_code
                
                # Small boost for text content type (vs images)
                if memory.content_type == "text":
                    final_score += boost_text_type
                
                memory_dict = memory.to_dict()
                memory_dict['similarity'] = float(vec_sim)  # Original vector similarity
                memory_dict['hybrid_score'] = float(final_score)  # Combined RRF score
                results.append(memory_dict)
            
            # Re-sort by final score after boosts
            results.sort(key=lambda x: x['hybrid_score'], reverse=True)
            
            logger.info(
                f"Hybrid search: {len(vec_results)} vector + {len(text_results)} text "
                f"candidates -> {len(results)} results"
            )
            
            return results
            
        except Exception as e:
            logger.warning(f"Hybrid search failed, falling back to vector search: {e}")
            # Fallback to vector-only search if hybrid fails
            return SearchEngine._vector_search(
                session, user_id, query_embedding, limit, offset, filters
            )

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
