"""
Remotive Agent — searches free Remotive API for remote tech jobs.
No API key required.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List
import re

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

# Map our categories to Remotive's category slugs
REMOTIVE_CATEGORY_MAP = {
    "Science & Technology": ["software-dev", "data", "devops-sysadmin", "qa"],
    "Manufacturing": ["product"],
    "Pharmacy & Biotech": ["data", "all-others"],
    "Defense & Military": ["all-others"],
    "Finance": ["finance-legal"],
    "Robotics & Automation": ["software-dev", "devops-sysadmin"],
    "Nuclear": ["all-others"],
    "Aerospace & Drones": ["all-others", "software-dev"],
}


class RemotiveAgent(BaseAgent):
    """Searches Remotive API for remote job postings."""

    name = "remotive"

    def is_configured(self) -> bool:
        return True  # No API key needed

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Remotive for a specific keyword."""
        jobs = []

        # Get the Remotive category slugs for filtering
        remotive_cats = REMOTIVE_CATEGORY_MAP.get(category, ["all-others"])

        # Search each mapped Remotive category
        for remotive_cat in remotive_cats:
            params = {
                "category": remotive_cat,
                "search": keyword,
                "limit": 50,
            }

            data = await self._request(
                "GET",
                config.REMOTIVE_BASE_URL,
                params=params,
            )

            if not data:
                continue

            listings = data.get("jobs", [])
            # Use 48h window since Remotive delays listings by ~24h
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

            for item in listings:
                # Client-side date filter (48h to account for Remotive's delay)
                pub_date_str = item.get("publication_date", "")
                if pub_date_str:
                    try:
                        pub_date = datetime.fromisoformat(
                            pub_date_str.replace("Z", "+00:00")
                        )
                        if pub_date < cutoff:
                            continue  # Older than 48 hours
                    except (ValueError, TypeError):
                        pass

                # Location
                location = item.get("candidate_required_location", "Remote")
                if not location:
                    location = "Anywhere"

                # Salary
                salary_str = item.get("salary", "")
                salary_min = None
                salary_max = None
                if salary_str:
                    numbers = re.findall(r'[\d]+', salary_str.replace(",", ""))
                    if len(numbers) >= 2:
                        try:
                            salary_min = float(numbers[0])
                            salary_max = float(numbers[1])
                        except ValueError:
                            pass
                    elif len(numbers) == 1:
                        try:
                            salary_min = float(numbers[0])
                        except ValueError:
                            pass

                # Job type from Remotive
                job_type_raw = item.get("job_type", "")
                emp_type = job_type_raw.replace("_", " ").title() if job_type_raw else "Full-Time"

                job = Job(
                    title=item.get("title", "Unknown"),
                    company=item.get("company_name", "Unknown"),
                    location=f"Remote - {location}",
                    url=item.get("url", ""),
                    source="remotive",
                    category=category,
                    posted_date=pub_date_str,
                    description=(item.get("description", ""))[:2000],
                    salary_min=salary_min,
                    salary_max=salary_max,
                    job_type="remote",
                    employment_type=emp_type,
                    remote=True,
                    search_keyword=keyword,
                )
                jobs.append(job)

        if jobs:
            logger.info(
                f"[remotive] Found {len(jobs)} jobs for '{keyword}' in {category}"
            )
        return jobs

    async def search_all_categories(self) -> List[Job]:
        """Search ALL categories (no longer skipping any)."""
        all_jobs = []

        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[remotive] Searching category: {category}")

            # Use more keywords per category (up to 8)
            subset = keywords[:8]
            tasks = [self.search(kw, category) for kw in subset]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"[remotive] Error searching '{subset[i]}': {result}"
                    )
                elif result:
                    all_jobs.extend(result)

        logger.info(f"[remotive] Total jobs found: {len(all_jobs)}")
        return all_jobs
