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
        # Convert libsql:// URL to https:// for Turso HTTP API
        api_url = db_url.replace("libsql://", "https://")
        if not api_url.startswith("https://"):
            api_url = f"https://{api_url}"
        self.db_url = api_url
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

    def _build_payload(self, sql: str, params: tuple = ()):
        """Build Turso v2 pipeline API payload."""
        args = []
        for p in params:
            if p is None:
                args.append({"type": "null", "value": None})
            elif isinstance(p, int):
                args.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                args.append({"type": "float", "value": p})
            else:
                args.append({"type": "text", "value": str(p)})

        stmt = {"sql": sql}
        if args:
            stmt["args"] = args

        return {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"}
            ]
        }

    def _parse_response(self, result: dict) -> List[Dict[str, Any]]:
        """Parse Turso v2 pipeline API response into rows."""
        results = result.get("results", [])
        if not results:
            return []

        first = results[0]
        response = first.get("response", {})
        resp_result = response.get("result", {})
        rows_data = resp_result.get("rows", [])
        cols = resp_result.get("cols", [])

        if not rows_data:
            return []

        # Convert from [{type, value}, ...] per cell to simple tuples
        parsed_rows = []
        for row in rows_data:
            parsed_row = []
            for cell in row:
                val = cell.get("value")
                cell_type = cell.get("type", "")
                if cell_type == "null" or val is None:
                    parsed_row.append(None)
                elif cell_type == "integer":
                    parsed_row.append(int(val))
                elif cell_type == "float":
                    parsed_row.append(float(val))
                else:
                    parsed_row.append(val)
            parsed_rows.append(tuple(parsed_row))

        return parsed_rows

    async def _execute(self, sql: str, params: tuple = (), timeout: float = 30.0) -> List[Dict[str, Any]]:
        """Execute a SQL statement via HTTP."""
        payload = self._build_payload(sql, params)
        url = f"{self.db_url}/v2/pipeline"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()

        return self._parse_response(result)

    def _execute_sync(self, sql: str, params: tuple = (), timeout: float = 30.0) -> List[Dict[str, Any]]:
        """Synchronous version of execute."""
        payload = self._build_payload(sql, params)
        url = f"{self.db_url}/v2/pipeline"

        with httpx.Client() as client:
            response = client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()

        return self._parse_response(result)

    def _execute_sync_with_cols(self, sql: str, params: tuple = (), timeout: float = 30.0):
        """Execute sync and also return column names from the response."""
        payload = self._build_payload(sql, params)
        url = f"{self.db_url}/v2/pipeline"

        with httpx.Client() as client:
            response = client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()

        rows = self._parse_response(result)

        # Extract column names from response
        cols = []
        results = result.get("results", [])
        if results:
            first = results[0]
            resp = first.get("response", {})
            resp_result = resp.get("result", {})
            cols = [c.get("name", f"col{i}") for i, c in enumerate(resp_result.get("cols", []))]

        return rows, cols

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

    def get_jobs_sync(self, hours: int = 0, limit: Optional[int] = 5000) -> List[Dict[str, Any]]:
        """Get jobs (synchronous for Streamlit)."""
        conditions = []
        params = []

        if hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            conditions.append("fetched_at >= ?")
            params.append(cutoff)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        if limit is not None:
            query = f"SELECT * FROM jobs {where} ORDER BY posted_date DESC LIMIT ?"
            params.append(limit)
        else:
            query = f"SELECT * FROM jobs {where} ORDER BY posted_date DESC"

        rows, columns = self._execute_sync_with_cols(query, tuple(params))

        if not rows or not columns:
            return []

        return [dict(zip(columns, row)) for row in rows]

    async def get_jobs(self, source=None, category=None, job_type=None, hours=24, search=None, limit=500, offset=0) -> List[Dict[str, Any]]:
        """Async version - delegates to sync since HTTP client is sync-safe."""
        return self.get_jobs_sync(hours=hours, limit=limit)

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
        runs_rows, run_columns = self._execute_sync_with_cols(
            "SELECT * FROM search_runs ORDER BY started_at DESC LIMIT 10"
        )
        runs = [dict(zip(run_columns, row)) for row in runs_rows] if run_columns else []

        return {
            "total": total,
            "by_source": by_source,
            "by_category": by_category,
            "by_type": by_type,
            "recent_runs": runs,
        }

    async def get_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Async version - delegates to sync."""
        return self.get_stats_sync(hours=hours)

    async def start_run(self) -> int:
        """Record the start of a search run."""
        self._execute_sync(
            "INSERT INTO search_runs (started_at) VALUES (?)",
            (datetime.utcnow().isoformat(),)
        )
        last_id = self._execute_sync("SELECT last_insert_rowid()")
        return last_id[0][0] if last_id else 0

    async def complete_run(self, run_id: int, total: int, new: int, dupes: int, errors: int, sources: str):
        """Record the completion of a search run."""
        self._execute_sync(
            "UPDATE search_runs SET completed_at=?, total_found=?, new_jobs=?, duplicates_skipped=?, errors=?, sources_searched=?, status='completed' WHERE id=?",
            (datetime.utcnow().isoformat(), total, new, dupes, errors, sources, run_id)
        )

    async def clean_old_jobs(self, days: int = 7) -> int:
        """Remove jobs older than specified days."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        # Count before delete
        count_rows = self._execute_sync(
            "SELECT COUNT(*) FROM jobs WHERE datetime(posted_date) <= datetime(?)",
            (cutoff,)
        )
        count = count_rows[0][0] if count_rows else 0
        if count > 0:
            self._execute_sync(
                "DELETE FROM jobs WHERE datetime(posted_date) <= datetime(?)",
                (cutoff,),
                timeout=120.0  # Bulk delete might take longer
            )
            logger.info(f"Cleaned up {count} jobs older than {days} days from Turso")
        return count

    async def vacuum(self):
        """Reclaim storage space by executing a VACUUM command."""
        logger.info("Running VACUUM to reclaim Turso storage space...")
        self._execute_sync("VACUUM", timeout=120.0)

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

        rows, all_columns = self._execute_sync_with_cols(query, tuple(params))

        return [dict(zip(all_columns, row)) for row in rows] if all_columns else []

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
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # Already inside an event loop (e.g. Streamlit) - use sync methods directly
            self._init_tables_sync()
        except RuntimeError:
            # No event loop running - safe to use asyncio.run
            asyncio.run(self.initialize())

    def _init_tables_sync(self):
        """Create tables using synchronous HTTP calls."""
        statements = [
            "CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, unique_hash TEXT UNIQUE NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL, url TEXT NOT NULL, source TEXT NOT NULL, category TEXT NOT NULL, posted_date TEXT NOT NULL, description TEXT DEFAULT '', salary_min REAL, salary_max REAL, job_type TEXT DEFAULT 'corporate', employment_type TEXT DEFAULT '', seniority TEXT DEFAULT '', remote INTEGER DEFAULT 0, search_keyword TEXT DEFAULT '', fetched_at TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now')))",
            "CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL, job_hash TEXT NOT NULL, profile_name TEXT NOT NULL, status TEXT DEFAULT 'queued', applied_at TEXT, cover_letter TEXT DEFAULT '', notes TEXT DEFAULT '', error_message TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), FOREIGN KEY (job_id) REFERENCES jobs(id))",
            "CREATE TABLE IF NOT EXISTS search_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, completed_at TEXT, total_found INTEGER DEFAULT 0, new_jobs INTEGER DEFAULT 0, duplicates_skipped INTEGER DEFAULT 0, errors INTEGER DEFAULT 0, sources_searched TEXT DEFAULT '', status TEXT DEFAULT 'running')",
            "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs(category)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date)",
            "CREATE INDEX IF NOT EXISTS idx_jobs_unique_hash ON jobs(unique_hash)",
            "CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id)",
            "CREATE INDEX IF NOT EXISTS idx_applications_profile ON applications(profile_name)",
            "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)",
        ]
        for stmt in statements:
            self._execute_sync(stmt)
        logger.info(f"Turso HTTP database initialized (sync) at {self.db_url}")

    def vacuum_sync(self):
        """Synchronous VACUUM."""
        logger.info("Running VACUUM to reclaim Turso storage space...")
        self._execute_sync("VACUUM", timeout=120.0)
