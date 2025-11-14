# db.py
import os
import asyncpg
from typing import List, Dict, Any

# Get DATABASE_URL from environment, fallback to SQLite-style path for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://jobfinder:secret@localhost:5432/jobfinder")

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS saved_search (
    id serial PRIMARY KEY,
    user_id bigint NOT NULL,
    query text NOT NULL,
    location text,
    remote_only boolean DEFAULT true,
    source text DEFAULT 'remotive',
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS seen_job (
    id serial PRIMARY KEY,
    search_id integer NOT NULL REFERENCES saved_search(id) ON DELETE CASCADE,
    job_unique_id text NOT NULL,
    seen_at timestamptz DEFAULT now(),
    UNIQUE(search_id, job_unique_id)
);
"""

# Global connection pool
pool: asyncpg.pool.Pool | None = None


async def init_db():
    """Initialize the database connection pool and create tables."""
    global pool
    if pool is not None:
        return  # Already initialized
    
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    
    # Create tables
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)


async def close_db():
    """Close the database connection pool."""
    global pool
    if pool:
        await pool.close()
        pool = None


async def add_saved_search(
    user_id: int, query: str, location: str | None, remote_only: bool, source: str
) -> int:
    """Add a new saved search and return its ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO saved_search (user_id, query, location, remote_only, source)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id, query, location, remote_only, source
        )
        return row["id"]


async def list_saved_searches(user_id: int) -> List[Dict[str, Any]]:
    """List all saved searches for a user."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM saved_search WHERE user_id = $1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(row) for row in rows]


async def remove_saved_search(search_id: int, user_id: int) -> bool:
    """Remove a saved search. Returns True if deleted, False if not found."""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM saved_search WHERE id = $1 AND user_id = $2",
            search_id, user_id
        )
        # asyncpg returns a string like "DELETE 1" or "DELETE 0"
        return result.split()[-1] != "0"


async def mark_job_seen(search_id: int, job_id: str) -> bool:
    """Mark a job as seen for a search. Returns True if newly seen, False if already seen."""
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO seen_job (search_id, job_unique_id) VALUES ($1, $2)",
                search_id, job_id
            )
            return True
        except asyncpg.UniqueViolationError:
            return False  # Already seen


async def get_all_saved_searches() -> List[Dict[str, Any]]:
    """Get all saved searches (for polling background task)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM saved_search ORDER BY created_at")
        return [dict(row) for row in rows]

