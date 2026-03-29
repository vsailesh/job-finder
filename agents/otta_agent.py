"""
Otta Agent — fetches jobs from Otta.com (tech startup job board).

No API key required — uses public API.
"""
import logging
from typing import List
from datetime import datetime
import re

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class OttaAgent(BaseAgent):
    """Fetches jobs from Otta.com."""

    name = "otta"

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword."""
        jobs = []

        # Otta API endpoint
        url = config.OTTA_BASE_URL or "https://www.otta.com/api/v0/jobs"

        params = {
            "q": keyword,
            "page": 1,
            "per_page": 50,
        }

        data = await self._request("GET", url, params=params)
        if not data:
            return []

        # Parse response
        jobs_data = data.get("jobs", [])

        for item in jobs_data:
            title = item.get("title", "")
            company = item.get("company", {}).get("name", "Unknown")

            if not title or not company:
                continue

            # Location
            location = item.get("location", {}).get("name", "Unknown")

            # Check for remote
            remote = item.get("is_remote", False) or "remote" in location.lower()

            # Salary
            salary_min = None
            salary_max = None
            salary_data = item.get("salary", {})
            if salary_data:
                try:
                    salary_min = salary_data.get("min")
                    salary_max = salary_data.get("max")
                except (AttributeError, TypeError):
                    pass

            # Employment type
            employment_type_map = {
                "permanent": "Full-Time",
                "contract": "Contract",
                "part_time": "Part-Time",
                "internship": "Internship",
            }
            employment_type_raw = item.get("employment_type", "permanent")
            employment_type = employment_type_map.get(employment_type_raw, "Full-Time")

            # Seniority
            seniority_map = {
                "entry_level": "entry",
                "mid_level": "mid",
                "senior_level": "senior",
                "executive": "executive",
            }
            seniority_raw = item.get("seniority", "")
            seniority = seniority_map.get(seniority_raw, "")

            # Posted date
            posted_date = item.get("published_at", datetime.utcnow().isoformat())

            # Description
            description = item.get("description", "")[:2000]

            job = Job(
                title=title,
                company=company,
                location=location,
                url=item.get("url", f"https://www.otta.com/jobs/{item.get('slug', '')}"),
                source=self.name,
                category=category,
                posted_date=posted_date,
                description=description,
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

    async def search_all_categories(self) -> List[Job]:
        """Override: Fetch all recent jobs and filter by category."""
        all_jobs = []

        # Fetch recent jobs
        url = config.OTTA_BASE_URL or "https://www.otta.com/api/v0/jobs"

        data = await self._request("GET", url, params={"per_page": 500})
        if not data:
            return []

        jobs_data = data.get("jobs", [])

        # Build keyword set for matching
        for item in jobs_data:
            title = item.get("title", "")
            description = item.get("description", "")
            combined_text = f"{title} {description}".lower()

            # Find matching keyword and category
            matched_keyword = None
            matched_category = None

            for category, keywords in config.SEARCH_CATEGORIES.items():
                for kw in keywords:
                    if kw.lower() in combined_text:
                        matched_keyword = kw
                        matched_category = category
                        break
                if matched_category:
                    break

            if not matched_category:
                continue

            company = item.get("company", {}).get("name", "Unknown")
            location = item.get("location", {}).get("name", "Unknown")
            remote = item.get("is_remote", False) or "remote" in location.lower()

            salary_data = item.get("salary", {})
            salary_min = salary_data.get("min") if salary_data else None
            salary_max = salary_data.get("max") if salary_data else None

            employment_type_map = {
                "permanent": "Full-Time",
                "contract": "Contract",
                "part_time": "Part-Time",
                "internship": "Internship",
            }
            employment_type_raw = item.get("employment_type", "permanent")
            employment_type = employment_type_map.get(employment_type_raw, "Full-Time")

            job = Job(
                title=title,
                company=company,
                location=location,
                url=item.get("url", ""),
                source=self.name,
                category=matched_category,
                posted_date=item.get("published_at", datetime.utcnow().isoformat()),
                description=description[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                job_type="corporate",
                employment_type=employment_type,
                remote=remote,
                search_keyword=matched_keyword,
            )
            all_jobs.append(job)

        logger.info(f"[{self.name}] Total jobs found: {len(all_jobs)}")
        return all_jobs
