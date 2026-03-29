"""
Pure Python Turso Cloud database client using HTTP REST API.
Works on Streamlit Cloud without requiring compilation.
"""
import httpx
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class TursoHTTPDatabase:
    """Turso database client using HTTP REST API (no compilation needed)."""

    def __init__(self, db_url: str, auth_token: str):
        self.db_url = db_url
        self.auth_token = auth_token
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    async def initialize(self):
        """Initialize database - create tables via HTTP."""
        # Create tables using SQL statements
        statements = [
            """
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
            """,
            """
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
            """,
            """
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
            """,
            # Create indexes
            "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date);",
            "CREATE INDEX IF NOT EXISTS idx_jobs_unique_hash ON jobs(unique_hash);",
            "CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);",
            "CREATE INDEX IF NOT EXISTS idx_applications_profile ON applications(profile_name);",
            "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);",
        ]

        for statement in statements:
            await self._execute(statement)

        logger.info(f"Turso HTTP database initialized at {self.db_url}")

    async def _execute(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SQL statement via HTTP."""
        payload = {"statements": [{"q": sql}]}
        if params:
            payload["statements"][0]["params"] = params

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.db_url,
                headers=self.headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()

        if result.get("results"):
            return result["results"][0].get("rows", [])
        return []

    def _execute_sync(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Synchronous version of execute."""
        payload = {"statements": [{"q": sql}]}
        if params:
            payload["statements"][0]["params"] = params

        with httpx.Client() as client:
            response = client.post(
                self.db_url,
                headers=self.headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()

        if result.get("results"):
            return result["results"][0].get("rows", [])
        return []

    async def insert_jobs(self, jobs: List[Any]) -> Dict[str, int]:
        """Insert jobs with deduplication."""
        inserted = 0
        skipped = 0

        for job in jobs:
            try:
                await self._execute(
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
                # Check for unique constraint violation
                if "UNIQUE constraint failed" in str(e):
                    skipped += 1
                else:
                    logger.error(f"Error inserting job: {e}")

        logger.info(f"Inserted {inserted} new jobs, skipped {skipped} duplicates")
        return {"inserted": inserted, "skipped": skipped}

    def get_jobs_sync(self, hours: int = 0, limit: int = 5000) -> List[Dict[str, Any]]:
        """Get jobs (synchronous for Streamlit)."""
        conditions = []
        params = []

        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM jobs {where} ORDER BY posted_date DESC LIMIT ?"
        params.append(limit)

        rows = self._execute_sync(query, tuple(params))

        # Convert rows to dict with column names
        if not rows:
            return []

        # Get column names from PRAGMA table_info
        columns_result = self._execute_sync("PRAGMA table_info(jobs)")
        columns = [row[1] for row in columns_result]

        return [dict(zip(columns, row)) for row in rows]

    def get_stats_sync(self, hours: int = 0) -> Dict[str, Any]:
        """Get stats (synchronous for Streamlit)."""
        conditions = []
        params = []

        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Total jobs
        total_rows = self._execute_sync(f"SELECT COUNT(*) FROM jobs {where}", tuple(params))
        total = total_rows[0][0] if total_rows else 0

        # By source
        source_rows = self._execute_sync(
            f"SELECT source, COUNT(*) as count FROM jobs {where} GROUP BY source ORDER BY count DESC",
            tuple(params)
        )
        by_source = {row[0]: row[1] for row in source_rows}

        # By category
        category_rows = self._execute_sync(
            f"SELECT category, COUNT(*) as count FROM jobs {where} GROUP BY category ORDER BY count DESC",
            tuple(params)
        )
        by_category = {row[0]: row[1] for row in category_rows}

        # By job type
        type_rows = self._execute_sync(
            f"SELECT job_type, COUNT(*) as count FROM jobs {where} GROUP BY job_type ORDER BY count DESC",
            tuple(params)
        )
        by_type = {row[0]: row[1] for row in type_rows}

        # Recent runs
        runs_rows = self._execute_sync(
            "SELECT * FROM search_runs ORDER BY started_at DESC LIMIT 10"
        )
        columns_result = self._execute_sync("PRAGMA table_info(search_runs)")
        run_columns = [row[1] for row in columns_result]
        runs = [dict(zip(run_columns, row)) for row in runs_rows]

        return {
            "total": total,
            "by_source": by_source,
            "by_category": by_category,
            "by_type": by_type,
            "recent_runs": runs,
        }

    def queue_application(self, job_id: int, job_hash: str, profile_name: str, cover_letter: str = "") -> int:
        """Queue a job for auto-apply."""
        # Check if already applied
        existing = self._execute_sync(
            "SELECT id FROM applications WHERE job_hash = ? AND profile_name = ?",
            (job_hash, profile_name)
        )
        if existing:
            return existing[0][0]

        result = self._execute_sync(
            """INSERT INTO applications (job_id, job_hash, profile_name, cover_letter, status)
               VALUES (?, ?, ?, ?, 'queued')""",
            (job_id, job_hash, profile_name, cover_letter)
        )

        # Get last inserted row ID
        last_id = self._execute_sync("SELECT last_insert_rowid()")
        return last_id[0][0] if last_id else 0

    def update_application_status(self, app_id: int, status: str, notes: str = "", error: str = ""):
        """Update application status."""
        applied_at = datetime.utcnow().isoformat() if status == "applied" else None
        self._execute_sync(
            """UPDATE applications SET status=?, notes=?, error_message=?,
               applied_at=COALESCE(?, applied_at) WHERE id=?""",
            (status, notes, error, applied_at, app_id)
        )

    def get_applications_sync(self, profile_name: str = "", status: str = "") -> List[Dict[str, Any]]:
        """Get applications with job details."""
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

        rows = self._execute_sync(query, tuple(params))

        # Get column names
        columns_result = self._execute_sync("PRAGMA table_info(applications)")
        app_columns = [row[1] for row in columns_result]

        # Add job columns
        job_columns = ["title", "company", "location", "url", "category", "job_type", "salary_min", "salary_max", "source"]
        all_columns = app_columns + job_columns

        return [dict(zip(all_columns, row)) for row in rows]

    def get_application_stats_sync(self) -> Dict[str, Any]:
        """Get application funnel stats."""
        status_rows = self._execute_sync("SELECT status, COUNT(*) FROM applications GROUP BY status")
        by_status = {row[0]: row[1] for row in status_rows}

        profiles_rows = self._execute_sync("SELECT COUNT(DISTINCT profile_name) FROM applications")
        profiles_used = profiles_rows[0][0] if profiles_rows else 0

        total_rows = self._execute_sync("SELECT COUNT(*) FROM applications")
        total = total_rows[0][0] if total_rows else 0

        return {
            "total": total,
            "by_status": by_status,
            "profiles_used": profiles_used,
        }

    def init_sync(self):
        """Synchronous initialization."""
        # Use async version in sync context
        import asyncio
        asyncio.run(self.initialize())

    def vacuum_sync(self):
        """Vacuum is not supported via HTTP API."""
        logger.info("Vacuum not available via HTTP API - use Turso CLI instead")
