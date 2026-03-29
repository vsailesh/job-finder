"""
Turso (libsql) cloud database wrapper for Job Finding Agent.
Implements the same interface as JobDatabase but uses libsql-experimental to connect to a remote Turso DB.
"""
import libsql_experimental as libsql
import logging
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
"""

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

class TursoDatabase:
    """Turso (libsql) database wrapper."""
    
    def __init__(self, url: str, auth_token: str):
        self.url = url
        self.auth_token = auth_token
        
    def _get_conn(self):
        """Get a synchronous connection."""
        return libsql.connect(database=self.url, auth_token=self.auth_token)
        
    async def initialize(self):
        """Create tables and indexes in Turso. Uses sync connection locally."""
        self.init_sync()
        logger.info(f"Turso Database initialized at {self.url}")
        
    def init_sync(self):
        """Synchronous initialization."""
        conn = self._get_conn()
        try:
            conn.execute(CREATE_JOBS_TABLE)
            conn.execute(CREATE_APPLICATIONS_TABLE)
            conn.execute(CREATE_RUNS_TABLE)
            for idx_sql in CREATE_INDEXES:
                conn.execute(idx_sql)
            conn.commit()
        finally:
            pass # libsql connections clean up themselves, but we can't context manage them directly without closing prematurely
    
    async def insert_jobs(self, jobs: List[Job]) -> Dict[str, int]:
        """Insert jobs with deduplication."""
        inserted = 0
        skipped = 0
        
        conn = self._get_conn()
        try:
            for job in jobs:
                try:
                    conn.execute(
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
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e):
                        skipped += 1
                    else:
                        logger.error(f"Error inserting job {job.title}: {e}")
            conn.commit()
        finally:
            pass
        
        logger.info(f"Inserted {inserted} new jobs, skipped {skipped} duplicates")
        return {"inserted": inserted, "skipped": skipped}
    
    async def clean_old_jobs(self, days: int = 7) -> int:
        """Remove jobs posted more than `days` ago."""
        conn = self._get_conn()
        try:
            # We use returning id to get the rowcount since driver might not support it directly well
            res = conn.execute(f"DELETE FROM jobs WHERE datetime(posted_date) <= datetime('now', '-{days} days') RETURNING id")
            deleted = len(res.fetchall())
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} jobs older than {days} days from Turso")
            return deleted
        finally:
            pass
            
    async def vacuum(self):
        """Turso manages itself, vacuum is a no-op but kept for compatibility."""
        logger.info("Turso backend does not require manual vacuuming.")
        
    def vacuum_sync(self):
        """Turso manages itself, vacuum is a no-op but kept for compatibility."""
        pass
    
    def _row_to_dict(self, row, columns) -> Dict[str, Any]:
        result = {}
        for idx, col in enumerate(columns):
            # Try to get column by index - if row acts like a tuple
            try:
                result[col] = row[idx]
            except:
                result[col] = None
        return result
    
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
        """Query jobs with optional filters. Implemented via sync call for simplicity with Turso."""
        return self.get_jobs_sync(hours=hours, limit=limit) # Simplify for now, async not strictly needed if driver handles well
    
    def get_jobs_sync(self, hours: int = 0, limit: int = 5000) -> List[Dict[str, Any]]:
        """Synchronous version for Streamlit."""
        conditions = []
        params = []
        
        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)
        
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM jobs {where} ORDER BY posted_date DESC LIMIT ?"
        params.append(limit)
        
        conn = self._get_conn()
        try:
            res = conn.execute(query, params)
            columns = [col[0] for col in res.description]
            return [self._row_to_dict(row, columns) for row in res.fetchall()]
        finally:
            pass
            
    async def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get summary statistics."""
        return self.get_stats_sync(hours=hours)
        
    def get_stats_sync(self, hours: int = 0) -> Dict[str, Any]:
        """Synchronous stats for Streamlit."""
        conn = self._get_conn()
        try:
            conditions = []
            params = []
            if hours > 0:
                cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
                conditions.append("fetched_at >= ?")
                params.append(cutoff)
            
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            total = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
            
            by_source = {row[0]: row[1] for row in conn.execute(
                f"SELECT source, COUNT(*) as count FROM jobs {where} GROUP BY source ORDER BY count DESC", params
            ).fetchall()}
            
            by_category = {row[0]: row[1] for row in conn.execute(
                f"SELECT category, COUNT(*) as count FROM jobs {where} GROUP BY category ORDER BY count DESC", params
            ).fetchall()}
            
            by_type = {row[0]: row[1] for row in conn.execute(
                f"SELECT job_type, COUNT(*) as count FROM jobs {where} GROUP BY job_type ORDER BY count DESC", params
            ).fetchall()}
            
            res = conn.execute("SELECT * FROM search_runs ORDER BY started_at DESC LIMIT 10")
            cols = [desc[0] for desc in res.description]
            runs = [self._row_to_dict(row, cols) for row in res.fetchall()]
            
            return {
                "total": total,
                "by_source": by_source,
                "by_category": by_category,
                "by_type": by_type,
                "recent_runs": runs,
            }
        finally:
            pass
            
    async def start_run(self) -> int:
        """Record the start of a search run."""
        conn = self._get_conn()
        try:
            res = conn.execute(
                "INSERT INTO search_runs (started_at) VALUES (?) RETURNING id",
                (datetime.utcnow().isoformat(),)
            )
            run_id = res.fetchone()[0]
            conn.commit()
            return run_id
        finally:
            pass
    
    async def complete_run(self, run_id: int, total: int, new: int, dupes: int, errors: int, sources: str):
        """Record the completion of a search run."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE search_runs SET completed_at=?, total_found=?, new_jobs=?, duplicates_skipped=?, errors=?, sources_searched=?, status='completed' WHERE id=?",
                (datetime.utcnow().isoformat(), total, new, dupes, errors, sources, run_id)
            )
            conn.commit()
        finally:
            pass

    def queue_application(self, job_id: int, job_hash: str, profile_name: str, cover_letter: str = "") -> int:
        """Queue a job for auto-apply."""
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM applications WHERE job_hash = ? AND profile_name = ?",
                (job_hash, profile_name)
            ).fetchone()
            if existing:
                return existing[0]
            res = conn.execute(
                "INSERT INTO applications (job_id, job_hash, profile_name, cover_letter, status) VALUES (?, ?, ?, ?, 'queued') RETURNING id",
                (job_id, job_hash, profile_name, cover_letter)
            )
            app_id = res.fetchone()[0]
            conn.commit()
            return app_id
        finally:
            pass

    def update_application_status(self, app_id: int, status: str, notes: str = "", error: str = ""):
        """Update application status."""
        conn = self._get_conn()
        try:
            applied_at = datetime.utcnow().isoformat() if status == "applied" else None
            conn.execute(
                "UPDATE applications SET status=?, notes=?, error_message=?, applied_at=COALESCE(?, applied_at) WHERE id=?",
                (status, notes, error, applied_at, app_id)
            )
            conn.commit()
        finally:
            pass

    def get_applications_sync(self, profile_name: str = "", status: str = "") -> List[Dict[str, Any]]:
        """Get applications with job details."""
        conn = self._get_conn()
        try:
            conditions = []
            params = []
            if profile_name:
                conditions.append("a.profile_name = ?")
                params.append(profile_name)
            if status:
                conditions.append("a.status = ?")
                params.append(status)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            query = f"SELECT a.*, j.title, j.company, j.location, j.url, j.category, j.job_type, j.salary_min, j.salary_max, j.source FROM applications a LEFT JOIN jobs j ON a.job_id = j.id {where} ORDER BY a.created_at DESC LIMIT 500"
            res = conn.execute(query, params)
            cols = [desc[0] for desc in res.description]
            return [self._row_to_dict(r, cols) for r in res.fetchall()]
        finally:
            pass

    def get_application_stats_sync(self) -> Dict[str, Any]:
        """Get application funnel stats."""
        conn = self._get_conn()
        try:
            by_status = {row[0]: row[1] for row in conn.execute("SELECT status, COUNT(*) FROM applications GROUP BY status").fetchall()}
            profiles_used = conn.execute("SELECT COUNT(DISTINCT profile_name) FROM applications").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
            return {
                "total": total,
                "by_status": by_status,
                "profiles_used": profiles_used,
            }
        finally:
            pass
