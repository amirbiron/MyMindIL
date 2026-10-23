"""
Re-embed stored memories with the current embedding model.

Every memory whose embedding_model differs from AIEngine.EMBED_MODEL - including
rows from before that column existed, where it is NULL - gets a fresh vector,
built from the same text the bot embeds when it saves a memory. Until a row is
re-embedded, semantic search skips it (keyword search still finds it).

Safe to run more than once: rows already on the current model are skipped, so
an interrupted run (network error, rate limit) resumes where it stopped.

Usage (for example from the Render Shell):
    python reembed_memories.py
"""
import logging
import sys

from ai_engine import AIEngine
from database import get_db_session, init_db
from models import Memory

logger = logging.getLogger(__name__)

BATCH_SIZE = 20


def _stale_filter():
    # ב-SQL הביטוי NULL != 'x' הוא NULL ולא TRUE, ו-"!=" היה מדלג בדיוק על השורות
    # הישנות (NULL). IS DISTINCT FROM מחזיר TRUE גם עבורן.
    return Memory.embedding_model.is_distinct_from(AIEngine.EMBED_MODEL)


def count_stale() -> int:
    with get_db_session() as session:
        return session.query(Memory).filter(_stale_filter()).count()


def reembed_all() -> int:
    """Re-embed every stale memory, one committed batch at a time. Returns the count."""
    done = 0
    seen = set()
    while True:
        with get_db_session() as session:
            batch = (
                session.query(Memory)
                .filter(_stale_filter())
                .order_by(Memory.id)
                .limit(BATCH_SIZE)
                .all()
            )
            if not batch:
                return done
            for memory in batch:
                # שורה שחוזרת אחרי שעודכנה פירושה שהעדכון לא נשמר - בלי העצירה הזו
                # הלולאה הייתה רצה לנצח על אותה אצווה.
                if memory.id in seen:
                    raise RuntimeError(f"Memory {memory.id} is still stale after re-embedding")
                seen.add(memory.id)
                fields = AIEngine.embed_memory(
                    memory.display_text, memory.search_text, memory.content_type
                )
                memory.embedding = fields['embedding']
                memory.embedding_model = fields['embedding_model']
        done += len(batch)
        logger.info(f"Re-embedded {done} memories so far")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # מוודא שעמודת embedding_model קיימת גם אם האפליקציה עוד לא עלתה אחרי העדכון.
    init_db()

    stale = count_stale()
    logger.info(f"{stale} memories need re-embedding with {AIEngine.EMBED_MODEL}")
    if not stale:
        return 0

    done = reembed_all()
    remaining = count_stale()
    logger.info(f"Done: re-embedded {done} memories, {remaining} still stale")
    return 0 if remaining == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
