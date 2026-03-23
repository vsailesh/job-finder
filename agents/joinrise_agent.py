"""
JoinRise Agent — searches the free Rise platform public jobs API.
No API key required. Covers wide range of industries.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

JOINRISE_URL = "https://api.joinrise.io/api/v1/jobs/public"


class JoinRiseAgent(BaseAgent):
    """Searches JoinRise API for job postings (no key required)."""

    name = "joinrise"

    def is_configured(self) -> bool:
        return True  # No API key needed

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search JoinRise for a specific keyword."""
        jobs = []

        params = {
            "page": 1,
            "limit": 50,
            "sort": "desc",
            "sortedBy": "createdAt",
            "search": keyword,
        }

        data = await self._request("GET", JOINRISE_URL, params=params)

        if not data:
            return jobs

        # Handle different response formats
        listings = []
        if isinstance(data, dict):
            listings = data.get("data", data.get("jobs", data.get("results", [])))
        elif isinstance(data, list):
            listings = data

        if not listings:
            return jobs

        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

        for item in listings:
            if not isinstance(item, dict):
                continue

            # Date filter
            created = item.get("createdAt", item.get("created_at", item.get("postedAt", "")))
            posted_date = ""
            if created:
                try:
                    if isinstance(created, (int, float)):
                        post_dt = datetime.fromtimestamp(created, tz=timezone.utc)
                    else:
                        post_dt = datetime.fromisoformat(
                            str(created).replace("Z", "+00:00")
                        )
                    if post_dt < cutoff:
                        continue
                    posted_date = post_dt.isoformat()
                except (ValueError, TypeError):
                    posted_date = str(created)

            # Location
            location = (
                item.get("location", "")
                or item.get("jobLoc", "")
                or item.get("city", "")
            )
            is_remote = item.get("remote", False) or item.get("isRemote", False)
            if is_remote:
                location = f"Remote{f' - {location}' if location else ''}"

            # Salary
            salary_min = item.get("salaryMin", item.get("salary_min"))
            salary_max = item.get("salaryMax", item.get("salary_max"))

            # Job type
            company = item.get("companyName", item.get("company", "Unknown"))
            job_type = "remote" if is_remote else "corporate"

            title = item.get("title", item.get("jobTitle", "Unknown"))

            job = Job(
                title=title,
                company=company if company else "Unknown",
                location=location or "United States",
                url=item.get("applyUrl", item.get("url", item.get("link", ""))),
                source="joinrise",
                category=category,
                posted_date=posted_date,
                description=(item.get("description", item.get("jobDescription", "")))[:2000],
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                job_type=job_type,
                employment_type=item.get("jobType", item.get("employmentType", "")),
                remote=is_remote or False,
                search_keyword=keyword,
            )
            jobs.append(job)

        if jobs:
            logger.info(f"[joinrise] Found {len(jobs)} jobs for '{keyword}' in {category}")
        return jobs
