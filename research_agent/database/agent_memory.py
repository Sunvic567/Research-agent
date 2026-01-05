import sqlite3
import json
import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger("agent_memory")
if not logger.handlers:
    # library should not configure root logging; attach a NullHandler by default
    logger.addHandler(logging.NullHandler())


class MemoryManager:
    """Manages the memory for the Research Using SQLites"""
    def __init__(self, db_path: str = 'memory/agent_memory.db'):
        """Initialize the memory manager"""
        self.db_path = db_path
        # ensure the db directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # initialize the database tables
        self._init_database()
        logger.info(f"Memory manager initialized with database: {db_path}")

    def _init_database(self):
        """Create database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_query TEXT NOT NULL,
                    task_type TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    user_provided_data TEXT,
                    agents_used TEXT,
                    success INTEGER DEFAULT 1
                )
            """)

            # Research results table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    query TEXT NOT NULL,
                    results TEXT NOT NULL,
                    sources TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)

            # Analyses table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    analysis TEXT NOT NULL,
                    key_insights TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)

            # Articles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER,
                    article TEXT NOT NULL,
                    quality_score REAL,
                    word_count INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)

            # Learnings table - for agent improvements
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    context TEXT,
                    success_pattern INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Similar queries cache - for faster responses
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT UNIQUE NOT NULL,
                    query TEXT NOT NULL,
                    result TEXT NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()
            logger.info("Database tables initialized")

    def start_conversation(self, user_query: str, task_type: str = None, user_provided_data: str = None) -> int:
        """Start and record a new conversation, return its id."""
        # Allow being called on the class (MemoryManager.start_conversation(...))
        # by instantiating a default manager and forwarding the call.
        if isinstance(self, type):
            return MemoryManager().start_conversation(user_query, task_type, user_provided_data)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversations (user_query, task_type, user_provided_data)
                VALUES (?, ?, ?)
            """, (user_query, task_type, user_provided_data))
            conn.commit()
            conv_id = cursor.lastrowid
            logger.info(f"Started conversation {conv_id}")
            return conv_id

    def end_conversation(self, conversation_id: int, agents_used: List[str], success: bool = True):
        """Mark a conversation as complete."""
        # Allow being called as MemoryManager.end_conversation(...)
        if isinstance(self, type):
            return MemoryManager().end_conversation(conversation_id, agents_used, success)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE conversations
                SET agents_used = ?, success = ?
                WHERE id = ?
            """, (json.dumps(agents_used), 1 if success else 0, conversation_id))
            conn.commit()
            logger.info(f"Ended conversation {conversation_id}")

    def save_research(self, conversation_id: int, query: str, results: str, sources: List[str] = None):
        """Save research results."""
        if isinstance(self, type):
            return MemoryManager().save_research(conversation_id, query, results, sources)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO research_results (conversation_id, query, results, sources)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, query, results, json.dumps(sources) if sources else None))
            conn.commit()
            logger.info(f"Saved research for conversation {conversation_id}")

    def get_similar_research(self, query: str, limit: int = 5) -> List[Dict]:
        """Find similar past research (simple keyword matching)."""
        if isinstance(self, type):
            return MemoryManager().get_similar_research(query, limit)
        
        if not query or not query.strip():
            return []

        # Extract word tokens (alphanumeric), prefer longer keywords, limit overall results
        tokens = re.findall(r'\w+', query.lower())
        keywords = [t for t in tokens if len(t) > 2][:5] or tokens[:3]

        results: List[Dict] = []
        seen = set()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for kw in keywords:
                cursor.execute("""
                    SELECT query, results, timestamp
                    FROM research_results
                    WHERE LOWER(query) LIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (f'%{kw}%', limit))

                for row in cursor.fetchall():
                    key = (row[0], row[2])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append({'query': row[0], 'results': row[1], 'timestamp': row[2]})
                    if len(results) >= limit:
                        break

                if len(results) >= limit:
                    break

        return results

    # ============================================
    # ANALYSIS MEMORY
    # ============================================
    
    def save_analysis(self, conversation_id: int, analysis: str, 
                     key_insights: List[str] = None):
        """Save analysis results."""
        if isinstance(self, type):
            return MemoryManager().save_analysis(conversation_id, analysis, key_insights)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analyses (conversation_id, analysis, key_insights)
                VALUES (?, ?, ?)
            """, (conversation_id, analysis, 
                  json.dumps(key_insights) if key_insights else None))
            conn.commit()
            logger.info(f"Saved analysis for conversation {conversation_id}")
    
    def get_past_analyses(self, topic: str, limit: int = 5) -> List[Dict]:
        """Get past analyses on similar topics."""
        if isinstance(self, type):
            return MemoryManager().get_past_analyses(topic, limit)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.analysis, a.key_insights, a.timestamp, c.user_query
                FROM analyses a
                JOIN conversations c ON a.conversation_id = c.id
                WHERE LOWER(c.user_query) LIKE ?
                ORDER BY a.timestamp DESC
                LIMIT ?
            """, (f'%{topic.lower()}%', limit))
            
            return [
                {
                    'analysis': r[0],
                    'key_insights': json.loads(r[1]) if r[1] else [],
                    'timestamp': r[2],
                    'original_query': r[3]
                }
                for r in cursor.fetchall()
            ]
    
    # ============================================
    # ARTICLE MEMORY
    # ============================================
    
    def save_article(self, conversation_id: int, article: str, 
                    quality_score: float = None):
        """Save generated article."""
        if isinstance(self, type):
            return MemoryManager().save_article(conversation_id, article, quality_score)
        
        word_count = len(article.split())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO articles (conversation_id, article, quality_score, word_count)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, article, quality_score, word_count))
            conn.commit()
            logger.info(f"Saved article for conversation {conversation_id}")
    
    def get_best_articles(self, topic: str = None, limit: int = 10) -> List[Dict]:
        """Get highest quality articles, optionally filtered by topic."""
        if isinstance(self, type):
            return MemoryManager().get_best_articles(topic, limit)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if topic:
                cursor.execute("""
                    SELECT a.article, a.quality_score, a.word_count, 
                           a.timestamp, c.user_query
                    FROM articles a
                    JOIN conversations c ON a.conversation_id = c.id
                    WHERE LOWER(c.user_query) LIKE ?
                    ORDER BY a.quality_score DESC, a.timestamp DESC
                    LIMIT ?
                """, (f'%{topic.lower()}%', limit))
            else:
                cursor.execute("""
                    SELECT a.article, a.quality_score, a.word_count, 
                           a.timestamp, c.user_query
                    FROM articles a
                    JOIN conversations c ON a.conversation_id = c.id
                    ORDER BY a.quality_score DESC, a.timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            return [
                {
                    'article': r[0],
                    'quality_score': r[1],
                    'word_count': r[2],
                    'timestamp': r[3],
                    'original_query': r[4]
                }
                for r in cursor.fetchall()
            ]
    
    # ============================================
    # LEARNING & IMPROVEMENT
    # ============================================
    
    def save_learning(self, agent_name: str, lesson: str, 
                     context: str = None, success_pattern: bool = True):
        """Save a learning for future improvement."""
        if isinstance(self, type):
            return MemoryManager().save_learning(agent_name, lesson, context, success_pattern)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learnings (agent_name, lesson, context, success_pattern)
                VALUES (?, ?, ?, ?)
            """, (agent_name, lesson, context, 1 if success_pattern else 0))
            conn.commit()
            logger.info(f"Saved learning for {agent_name}")
    
    def get_learnings(self, agent_name: str = None, 
                     success_only: bool = True, limit: int = 20) -> List[Dict]:
        """Retrieve learnings for an agent."""
        if isinstance(self, type):
            return MemoryManager().get_learnings(agent_name, success_only, limit)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if agent_name:
                if success_only:
                    cursor.execute("""
                        SELECT lesson, context, timestamp
                        FROM learnings
                        WHERE agent_name = ? AND success_pattern = 1
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (agent_name, limit))
                else:
                    cursor.execute("""
                        SELECT lesson, context, timestamp, success_pattern
                        FROM learnings
                        WHERE agent_name = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """, (agent_name, limit))
            else:
                # return same column order (lesson, context, timestamp) for consistency
                cursor.execute("""
                    SELECT lesson, context, timestamp
                    FROM learnings
                    WHERE success_pattern = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (1 if success_only else 0, limit))
            
            return [
                {
                    'lesson': r[0],
                    'context': r[1] if len(r) > 1 else None,
                    'timestamp': r[2] if len(r) > 2 else None,
                    'success_pattern': r[3] if len(r) > 3 else None
                }
                for r in cursor.fetchall()
            ]
    
    # ============================================
    # QUERY CACHING
    # ============================================
    
    def get_cached_result(self, query: str) -> Optional[str]:
        """Check if we have a cached result for this query."""
        if isinstance(self, type):
            return MemoryManager().get_cached_result(query)
        
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT result FROM query_cache WHERE query_hash = ?
            """, (query_hash,))
            
            result = cursor.fetchone()
            if result:
                # Update hit count and last accessed
                cursor.execute("""
                    UPDATE query_cache 
                    SET hit_count = hit_count + 1, 
                        last_accessed = CURRENT_TIMESTAMP
                    WHERE query_hash = ?
                """, (query_hash,))
                conn.commit()
                logger.info(f"Cache hit for query: {query[:50]}...")
                return result[0]
            
            return None
    
    def cache_result(self, query: str, result: str):
        """Cache a result for future use."""
        if isinstance(self, type):
            return MemoryManager().cache_result(query, result)
        
        query_hash = hashlib.sha256(query.lower().strip().encode()).hexdigest()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Upsert: insert new or update existing result + last_accessed
            cursor.execute("""
                INSERT INTO query_cache (query_hash, query, result, hit_count, last_accessed, created_at)
                VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(query_hash) DO UPDATE SET
                    result = excluded.result,
                    last_accessed = CURRENT_TIMESTAMP
            """, (query_hash, query, result))
            conn.commit()
            logger.info(f"Cached result for query: {query[:50]}...")
    
    # ============================================
    # STATISTICS & ANALYTICS
    # ============================================
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall system statistics.""" 
        if isinstance(self, type):
            return MemoryManager().get_statistics()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Total conversations
            cursor.execute("SELECT COUNT(*) FROM conversations")
            stats['total_conversations'] = cursor.fetchone()[0]
            
            # Successful conversations
            cursor.execute("SELECT COUNT(*) FROM conversations WHERE success = 1")
            stats['successful_conversations'] = cursor.fetchone()[0]
            
            # Total research queries
            cursor.execute("SELECT COUNT(*) FROM research_results")
            stats['total_research_queries'] = cursor.fetchone()[0]
            
            # Total analyses
            cursor.execute("SELECT COUNT(*) FROM analyses")
            stats['total_analyses'] = cursor.fetchone()[0]
            
            # Total articles
            cursor.execute("SELECT COUNT(*) FROM articles")
            stats['total_articles'] = cursor.fetchone()[0]
            
            # Average article quality
            cursor.execute("SELECT AVG(quality_score) FROM articles WHERE quality_score IS NOT NULL")
            avg_quality = cursor.fetchone()[0]
            stats['average_article_quality'] = round(avg_quality, 2) if avg_quality is not None else None
            
            # Cache statistics
            cursor.execute("SELECT COUNT(*), SUM(hit_count) FROM query_cache")
            cache_stats = cursor.fetchone()
            stats['cached_queries'] = cache_stats[0]
            stats['total_cache_hits'] = cache_stats[1] or 0
            
            # Most common task types
            cursor.execute("""
                SELECT task_type, COUNT(*) as count 
                FROM conversations 
                WHERE task_type IS NOT NULL
                GROUP BY task_type 
                ORDER BY count DESC 
                LIMIT 5
            """)
            stats['top_task_types'] = dict(cursor.fetchall())
            
            return stats
    
    def clear_old_cache(self, days: int = 30):
        """Clear cache entries older than specified days."""
        if isinstance(self, type):
            return MemoryManager().clear_old_cache(days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("""
                DELETE FROM query_cache 
                WHERE last_accessed < ?
            """, (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Cleared {deleted} old cache entries")
            return deleted