"""
Arbeitnow Agent — searches the free Arbeitnow job board API.
No API key required. Covers tech/remote jobs globally.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowAgent(BaseAgent):
    """Searches Arbeitnow API for job postings (no key required)."""

    name = "arbeitnow"

    def is_configured(self) -> bool:
        return True  # No API key needed

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Arbeitnow for a specific keyword."""
        jobs = []
        max_pages = 3

        for page in range(1, max_pages + 1):
            params = {"page": page}
            data = await self._request("GET", ARBEITNOW_URL, params=params)

            if not data:
                break

            listings = data.get("data", [])
            if not listings:
                break

            keyword_lower = keyword.lower()
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

            for item in listings:
                title = item.get("title", "")
                desc = item.get("description", "")
                tags = " ".join(item.get("tags", []))
                searchable = f"{title} {desc} {tags}".lower()

                # Keyword match
                if keyword_lower not in searchable:
                    continue

                # Date filter — Arbeitnow uses Unix timestamps
                created_at = item.get("created_at")
                posted_date = ""
                if created_at:
                    try:
                        post_dt = datetime.fromtimestamp(created_at, tz=timezone.utc)
                        if post_dt < cutoff:
                            continue
                        posted_date = post_dt.isoformat()
                    except (ValueError, TypeError, OSError):
                        posted_date = ""

                # Location
                location = item.get("location", "Remote")
                is_remote = item.get("remote", False)
                if is_remote and location:
                    location = f"Remote - {location}"
                elif is_remote:
                    location = "Remote"

                # Job type detection
                company = item.get("company_name", "Unknown")
                job_type = "remote" if is_remote else "corporate"
                gov_kw = ["government", "federal", "state of", "department of", "public sector"]
                if any(gk in company.lower() for gk in gov_kw):
                    job_type = "federal"

                job = Job(
                    title=title or "Unknown",
                    company=company,
                    location=location or "Not specified",
                    url=item.get("url", ""),
                    source="arbeitnow",
                    category=category,
                    posted_date=posted_date,
                    description=(desc or "")[:2000],
                    job_type=job_type,
                    employment_type=item.get("job_types", ["Full-Time"])[0] if item.get("job_types") else "Full-Time",
                    remote=is_remote or False,
                    search_keyword=keyword,
                )
                jobs.append(job)

            # Check if there are more pages
            links = data.get("links", {})
            if not links.get("next"):
                break

        if jobs:
            logger.info(f"[arbeitnow] Found {len(jobs)} jobs for '{keyword}' in {category}")
        return jobs
