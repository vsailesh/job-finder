"""
Async SQLite database manager for storing and querying job postings.
"""
import aiosqlite
import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from models.job import Job

logger = logging.getLogger(__name__)

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    posted_date TEXT NOT NULL,
    description TEXT DEFAULT '',
    salary_min REAL,
    salary_max REAL,
    job_type TEXT DEFAULT 'corporate',
    employment_type TEXT DEFAULT '',
    seniority TEXT DEFAULT '',
    remote INTEGER DEFAULT 0,
    search_keyword TEXT DEFAULT '',
    fetched_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_APPLICATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    job_hash TEXT NOT NULL,
    profile_name TEXT NOT NULL,
    status TEXT DEFAULT 'queued',
    applied_at TEXT,
    cover_letter TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);",
    "CREATE INDEX IF NOT EXISTS idx_jobs_unique_hash ON jobs(unique_hash);",
    "CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);",
    "CREATE INDEX IF NOT EXISTS idx_applications_profile ON applications(profile_name);",
    "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);",
]

CREATE_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS search_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    total_found INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    sources_searched TEXT DEFAULT '',
    status TEXT DEFAULT 'running'
);
"""



class JobDatabase:
    """Async SQLite database for job postings."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    async def initialize(self):
        """Create tables and indexes."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.execute(CREATE_JOBS_TABLE)
            await db.execute(CREATE_APPLICATIONS_TABLE)
            await db.execute(CREATE_RUNS_TABLE)
            for idx_sql in CREATE_INDEXES:
                await db.execute(idx_sql)
            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    async def insert_jobs(self, jobs: List[Job]) -> Dict[str, int]:
        """
        Insert jobs with deduplication.
        Returns dict with 'inserted' and 'skipped' counts.
        """
        inserted = 0
        skipped = 0
        
        async with aiosqlite.connect(self.db_path) as db:
            for job in jobs:
                try:
                    await db.execute(
                        """INSERT INTO jobs 
                           (unique_hash, title, company, location, url, source, category,
                            posted_date, description, salary_min, salary_max, job_type,
                            employment_type, seniority, remote, search_keyword, fetched_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            job.unique_hash, job.title, job.company, job.location,
                            job.url, job.source, job.category, job.posted_date,
                            job.description, job.salary_min, job.salary_max,
                            job.job_type, job.employment_type, job.seniority,
                            1 if job.remote else 0, job.search_keyword, job.fetched_at,
                        )
                    )
                    inserted += 1
                except aiosqlite.IntegrityError:
                    skipped += 1
            await db.commit()
        
        logger.info(f"Inserted {inserted} new jobs, skipped {skipped} duplicates")
        return {"inserted": inserted, "skipped": skipped}
    
    async def clean_old_jobs(self, days: int = 7) -> int:
        """Remove jobs posted more than `days` ago."""
        async with aiosqlite.connect(self.db_path) as db:
            query = f"DELETE FROM jobs WHERE datetime(posted_date) <= datetime('now', '-{days} days')"
            cursor = await db.execute(query)
            await db.commit()
            
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} jobs older than {days} days")
            return deleted
    
    async def get_jobs(
        self,
        source: Optional[str] = None,
        category: Optional[str] = None,
        job_type: Optional[str] = None,
        hours: int = 24,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Query jobs with optional filters."""
        conditions = []
        params = []
        
        if source:
            conditions.append("source = ?")
            params.append(source)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if job_type:
            conditions.append("job_type = ?")
            params.append(job_type)
        if hours:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)
        if search:
            conditions.append("(title LIKE ? OR company LIKE ? OR description LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term, term])
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""SELECT * FROM jobs {where} 
                    ORDER BY posted_date DESC LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary statistics."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Total jobs
            cursor = await db.execute(
                "SELECT COUNT(*) FROM jobs WHERE fetched_at >= ?", (cutoff,)
            )
            total = (await cursor.fetchone())[0]
            
            # By source
            cursor = await db.execute(
                """SELECT source, COUNT(*) as count FROM jobs 
                   WHERE fetched_at >= ? GROUP BY source ORDER BY count DESC""",
                (cutoff,)
            )
            by_source = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # By category
            cursor = await db.execute(
                """SELECT category, COUNT(*) as count FROM jobs 
                   WHERE fetched_at >= ? GROUP BY category ORDER BY count DESC""",
                (cutoff,)
            )
            by_category = {row[0]: row[1] for row in await cursor.fetchall()}
            
            # By job type
            cursor = await db.execute(
                """SELECT job_type, COUNT(*) as count FROM jobs 
                   WHERE fetched_at >= ? GROUP BY job_type ORDER BY count DESC""",
                (cutoff,)
            )
            by_type = {row[0]: row[1] for row in await cursor.fetchall()}
            
            return {
                "total": total,
                "by_source": by_source,
                "by_category": by_category,
                "by_type": by_type,
            }
    
    async def start_run(self) -> int:
        """Record the start of a search run."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO search_runs (started_at) VALUES (?)",
                (datetime.utcnow().isoformat(),)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def complete_run(self, run_id: int, total: int, new: int, dupes: int, errors: int, sources: str):
        """Record the completion of a search run."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE search_runs SET completed_at=?, total_found=?, new_jobs=?,
                   duplicates_skipped=?, errors=?, sources_searched=?, status='completed'
                   WHERE id=?""",
                (datetime.utcnow().isoformat(), total, new, dupes, errors, sources, run_id)
            )
            await db.commit()
    
    def get_jobs_sync(self, hours: int = 0, limit: int = 5000) -> List[Dict[str, Any]]:
        """Synchronous version for Streamlit (which doesn't support async well)."""
        conditions = []
        params = []
        
        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM jobs {where} ORDER BY posted_date DESC LIMIT ?"
        params.append(limit)
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    
    def get_stats_sync(self, hours: int = 0) -> Dict[str, Any]:
        """Synchronous stats for Streamlit."""
        conn = sqlite3.connect(self.db_path)
        
        conditions = []
        params = []
        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        cursor = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params)
        total = cursor.fetchone()[0]
        
        cursor = conn.execute(
            f"SELECT source, COUNT(*) as count FROM jobs {where} GROUP BY source ORDER BY count DESC",
            params,
        )
        by_source = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor = conn.execute(
            f"SELECT category, COUNT(*) as count FROM jobs {where} GROUP BY category ORDER BY count DESC",
            params,
        )
        by_category = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor = conn.execute(
            f"SELECT job_type, COUNT(*) as count FROM jobs {where} GROUP BY job_type ORDER BY count DESC",
            params,
        )
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Recent runs
        cursor = conn.execute(
            "SELECT * FROM search_runs ORDER BY started_at DESC LIMIT 10"
        )
        cols = [desc[0] for desc in cursor.description]
        runs = [dict(zip(cols, row)) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "total": total,
            "by_source": by_source,
            "by_category": by_category,
            "by_type": by_type,
            "recent_runs": runs,
        }

    # ─── Application Tracking Methods ─────────────────────────

    def queue_application(self, job_id: int, job_hash: str, profile_name: str, cover_letter: str = "") -> int:
        """Queue a job for auto-apply."""
        conn = sqlite3.connect(self.db_path)
        # Check if already applied
        existing = conn.execute(
            "SELECT id FROM applications WHERE job_hash = ? AND profile_name = ?",
            (job_hash, profile_name)
        ).fetchone()
        if existing:
            conn.close()
            return existing[0]
        cursor = conn.execute(
            """INSERT INTO applications (job_id, job_hash, profile_name, cover_letter, status)
               VALUES (?, ?, ?, ?, 'queued')""",
            (job_id, job_hash, profile_name, cover_letter)
        )
        conn.commit()
        app_id = cursor.lastrowid
        conn.close()
        return app_id

    def update_application_status(self, app_id: int, status: str, notes: str = "", error: str = ""):
        """Update application status."""
        conn = sqlite3.connect(self.db_path)
        applied_at = datetime.utcnow().isoformat() if status == "applied" else None
        conn.execute(
            """UPDATE applications SET status=?, notes=?, error_message=?,
               applied_at=COALESCE(?, applied_at) WHERE id=?""",
            (status, notes, error, applied_at, app_id)
        )
        conn.commit()
        conn.close()

    def get_applications_sync(self, profile_name: str = "", status: str = "") -> List[Dict[str, Any]]:
        """Get applications with job details."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conditions = []
        params = []
        if profile_name:
            conditions.append("a.profile_name = ?")
            params.append(profile_name)
        if status:
            conditions.append("a.status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""SELECT a.*, j.title, j.company, j.location, j.url, j.category, j.job_type,
                           j.salary_min, j.salary_max, j.source
                    FROM applications a
                    LEFT JOIN jobs j ON a.job_id = j.id
                    {where}
                    ORDER BY a.created_at DESC LIMIT 500"""
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        conn.close()
        return rows

    def get_application_stats_sync(self) -> Dict[str, Any]:
        """Get application funnel stats."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status")
        by_status = {row[0]: row[1] for row in cursor.fetchall()}
        cursor = conn.execute("SELECT COUNT(DISTINCT profile_name) FROM applications")
        profiles_used = cursor.fetchone()[0]
        cursor = conn.execute("SELECT COUNT(*) FROM applications")
        total = cursor.fetchone()[0]
        conn.close()
        return {
            "total": total,
            "by_status": by_status,
            "profiles_used": profiles_used,
        }

    def init_sync(self):
        """Synchronous initialization for Streamlit."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(CREATE_JOBS_TABLE)
        conn.execute(CREATE_APPLICATIONS_TABLE)
        conn.execute(CREATE_RUNS_TABLE)
        for idx_sql in CREATE_INDEXES:
            conn.execute(idx_sql)
        conn.commit()
        conn.close()
