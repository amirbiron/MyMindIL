"""
Database models for MyMindIL
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from database import Base
from config import Config


class Memory(Base):
    """
    Main table storing all user memories with semantic search capabilities
    """
    __tablename__ = 'memories'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(BigInteger, nullable=False, index=True)
    
    # Content information
    content_type = Column(String(50), nullable=False)  # text, image, voice, link
    original_content = Column(Text, nullable=False)  # Original text, URL, or file_id
    
    # AI-generated fields
    display_text = Column(Text, nullable=False)  # Hebrew summary for display
    search_text = Column(Text, nullable=False)  # Optimized text for keyword search
    # NOTE: "metadata" is a reserved attribute name in SQLAlchemy Declarative.
    # Keep the DB column name as "metadata" but expose it as "meta" in Python.
    meta = Column("metadata", JSONB, nullable=False, default=dict)  # Structured data
    
    # Vector embedding for semantic search
    embedding = Column(Vector(Config.EMBEDDING_DIMENSION), nullable=False)
    # המודל שיצר את הווקטור. וקטורים ממודלים שונים אינם ברי השוואה, ולכן החיפוש
    # הסמנטי משווה רק לשורות של המודל הנוכחי, ו-reembed_memories.py מעדכן את השאר.
    # NULL = שורה מלפני העמודה, שנוצרה ב-text-embedding-004 (נסגר ב-14.1.2026).
    embedding_model = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        # HNSW index for vector similarity search (cosine distance)
        Index(
            'idx_memories_embedding_hnsw',
            'embedding',
            postgresql_using='hnsw',
            postgresql_with={'m': 16, 'ef_construction': 64},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
        # GIN index for JSONB metadata
        Index('idx_memories_metadata', 'metadata', postgresql_using='gin'),
        # Composite index for user queries
        Index('idx_memories_user_created', 'user_id', 'created_at'),
    )
    
    def to_dict(self):
        """Convert model to dictionary for JSON serialization"""
        return {
            'id': str(self.id),
            'user_id': self.user_id,
            'content_type': self.content_type,
            'original_content': self.original_content,
            'display_text': self.display_text,
            'search_text': self.search_text,
            'metadata': self.meta,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
    
    def __repr__(self):
        return f"<Memory {self.id} - {self.content_type} for user {self.user_id}>"
