"""
ZipRecruiter Agent — fetches jobs from ZipRecruiter API.

Requires a free API key from https://www.ziprecruiter.com/hiring/api
"""
import logging
from typing import List, Optional
from datetime import datetime, timedelta

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class ZipRecruiterAgent(BaseAgent):
    """Fetches jobs from ZipRecruiter API."""

    name = "ziprecruiter"

    def __init__(self):
        super().__init__()
        self.api_key = config.ZIPRECRUITER_API_KEY

    def is_configured(self) -> bool:
        """Check if the agent has required API keys configured."""
        return bool(self.api_key)

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword."""
        if not self.is_configured():
            logger.warning(f"[{self.name}] Not configured — missing API key")
            return []

        jobs = []

        # ZipRecruiter API search endpoint
        url = config.ZIPRECRUITER_BASE_URL or "https://api.ziprecruiter.com/jobs-app/version"
        params = {
            "api_key": self.api_key,
            "search": keyword,
            "location": "United States",
            "radius": 100,
            "days_ago": 1,  # Last 24 hours
            "jobs_per_page": 50,
            "page": 1,
        }

        data = await self._request("GET", url, params=params)
        if not data:
            return []

        # Parse response
        jobs_data = data.get("jobs", [])

        for item in jobs_data:
            title = item.get("job_title", "")
            company = item.get("hiring_company", {}).get("name", "Unknown")

            # Skip if missing essential fields
            if not title or not company:
                continue

            # Location
            location = item.get("location", "Unknown")

            # Check for remote
            remote = "remote" in location.lower() or "remote" in title.lower()

            # Salary extraction
            salary_min = None
            salary_max = None
            salary_raw = item.get("salary", "")
            if salary_raw:
                # Parse salary from string
                import re
                match = re.search(r'\$?([\d,]+)(?:\s*-\s*\$?([\d,]+))?', salary_raw.replace(',', ''))
                if match:
                    try:
                        salary_min = float(match.group(1).replace(',', ''))
                        if match.group(2):
                            salary_max = float(match.group(2).replace(',', ''))
                        # Normalize if salary looks like hourly
                        if salary_min < 200:
                            salary_min *= 2080  # Hourly to annual
                        if salary_max and salary_max < 200:
                            salary_max *= 2080
                    except (ValueError, AttributeError):
                        pass

            # Employment type
            employment_type = item.get("employment_type", "Full-Time")
            if "contract" in employment_type.lower():
                employment_type = "Contract"
            elif "part" in employment_type.lower():
                employment_type = "Part-Time"

            # Seniority
            seniority = ""
            title_lower = title.lower()
            if any(w in title_lower for w in ["senior", "sr.", "sr ", "lead", "principal"]):
                seniority = "senior"
            elif any(w in title_lower for w in ["junior", "jr.", "jr ", "entry"]):
                seniority = "entry"
            elif any(w in title_lower for w in ["manager", "director", "vp"]):
                seniority = "executive"

            job = Job(
                title=title,
                company=company,
                location=location,
                url=item.get("job_url", ""),
                source=self.name,
                category=category,
                posted_date=item.get("posted_time", datetime.utcnow().isoformat()),
                description=item.get("job_description", "")[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                job_type="corporate",
                employment_type=employment_type,
                seniority=seniority,
                remote=remote,
                search_keyword=keyword,
            )
            jobs.append(job)

        logger.info(f"[{self.name}] Found {len(jobs)} jobs for '{keyword}'")
        return jobs
