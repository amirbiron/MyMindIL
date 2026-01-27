"""
Database connection and session management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
from config import Config
import logging

logger = logging.getLogger(__name__)

# Create base class for models
Base = declarative_base()

# Create engine with connection pooling
engine = create_engine(
    Config.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections before using
    echo=Config.DEBUG,
)

# Create session factory
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


@contextmanager
def get_db_session():
    """
    Provide a transactional scope for database operations
    Usage:
        with get_db_session() as session:
            session.add(obj)
            session.commit()
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        session.close()


def ensure_search_infra(conn):
    """
    Ensure search infrastructure is set up (text + vector indexes).

    This runs DDL that create_all() doesn't handle well:
    - GENERATED ALWAYS AS ... STORED columns
    - Custom indexes with specific opclasses

    Safe to run multiple times (uses IF NOT EXISTS).
    """
    ddl_statements = [
        # pgvector extension (redundant but safe)
        "CREATE EXTENSION IF NOT EXISTS vector;",
        # pg_trgm extension for trigram similarity
        "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
        
        # Add tsvector generated column for full-text search
        # Uses 'simple' config for Hebrew + code (no stemming)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'memories' AND column_name = 'search_tsv'
            ) THEN
                ALTER TABLE memories
                ADD COLUMN search_tsv tsvector
                GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(search_text, ''))
                ) STORED;
            END IF;
        END $$;
        """,
        
        # GIN index for full-text search on search_tsv
        """
        CREATE INDEX IF NOT EXISTS idx_memories_search_tsv
        ON memories USING gin (search_tsv);
        """,

        # GIN trigram index for fuzzy text search
        """
        CREATE INDEX IF NOT EXISTS idx_memories_search_trgm
        ON memories USING gin (
            (coalesce(search_text, '') || ' ' || coalesce(display_text, '')) gin_trgm_ops
        );
        """,
        
        # HNSW index for vector similarity search (cosine distance)
        # This is also defined in the model, but we ensure it exists here too
        """
        CREATE INDEX IF NOT EXISTS idx_memories_embedding_hnsw
        ON memories USING hnsw (embedding vector_cosine_ops);
        """,
    ]
    
    for ddl in ddl_statements:
        try:
            conn.execute(text(ddl))
        except Exception as e:
            # Log but don't fail - some statements might fail on certain DB versions
            logger.warning(f"DDL statement warning: {e}")
    
    conn.commit()
    logger.info("Search infrastructure verified/created")


def init_db():
    """
    Initialize database: create pgvector extension and all tables
    """
    try:
        # Enable pgvector extension
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            logger.info("pgvector extension enabled")
        
        # Create all tables
        Base.metadata.create_all(engine)
        logger.info("Database tables created successfully")
        
        # Ensure search infrastructure (tsvector, indexes)
        with engine.connect() as conn:
            ensure_search_infra(conn)
        
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def check_db_connection():
    """
    Check if database connection is working
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


def get_db_stats():
    """
    Get database statistics for monitoring
    """
    try:
        with get_db_session() as session:
            result = session.execute(text("""
                SELECT 
                    COUNT(*) as total_memories,
                    COUNT(DISTINCT user_id) as total_users
                FROM memories
            """))
            stats = result.fetchone()
            
            return {
                'total_memories': stats[0] if stats else 0,
                'total_users': stats[1] if stats else 0,
                'connection_pool_size': engine.pool.size(),
                'connection_pool_overflow': engine.pool.overflow(),
            }
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return {}
