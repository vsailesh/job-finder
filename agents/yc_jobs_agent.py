"""
YC Jobs Agent — fetches jobs from workatastartup.com (YC-backed startups).

No API key required — uses public API.
"""
import logging
from typing import List
from datetime import datetime, timedelta
import re

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class YCJobsAgent(BaseAgent):
    """Fetches jobs from YC Jobs (workatastartup.com)."""

    name = "yc_jobs"

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword."""
        jobs = []

        # YC Jobs public API
        url = config.YC_JOBS_BASE_URL or "https://www.workatastartup.com/api/jobs"

        params = {
            "q": keyword,
            "limit": 50,
        }

        data = await self._request("GET", url, params=params)
        if not data:
            return []

        # Parse response
        jobs_data = data.get("data", []) if isinstance(data, dict) else data

        for item in jobs_data:
            title = item.get("title", "")
            company_info = item.get("company", {})
            company = company_info.get("name", "Unknown")

            if not title or not company:
                continue

            # Location
            location_data = item.get("location", {})
            location = location_data.get("city", "") or location_data.get("country", "Unknown")

            # Check for remote
            remote = item.get("remote", False) or "remote" in location.lower()

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
            employment_type = item.get("type", "Full-Time")
            if employment_type == "contract":
                employment_type = "Contract"
            elif employment_type == "part-time":
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

            # Posted date
            posted_date = item.get("created_at", datetime.utcnow().isoformat())

            # Description
            description = item.get("description", "")[:2000]

            job = Job(
                title=title,
                company=company,
                location=location,
                url=item.get("url", f"https://www.workatastartup.com/jobs/{item.get('slug', '')}"),
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
        """Override: YC Jobs doesn't support keyword search well, fetch all and filter."""
        all_jobs = []

        # Fetch recent jobs
        url = config.YC_JOBS_BASE_URL or "https://www.workatastartup.com/api/jobs"

        data = await self._request("GET", url, params={"limit": 500})
        if not data:
            return []

        jobs_data = data.get("data", []) if isinstance(data, dict) else data

        # Build keyword set for matching
        all_keywords = set()
        for keywords in config.SEARCH_CATEGORIES.values():
            all_keywords.update(k.lower() for k in keywords)

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

            company_info = item.get("company", {})
            company = company_info.get("name", "Unknown")

            location_data = item.get("location", {})
            location = location_data.get("city", "") or location_data.get("country", "Unknown")

            remote = item.get("remote", False) or "remote" in location.lower()

            salary_data = item.get("salary", {})
            salary_min = salary_data.get("min") if salary_data else None
            salary_max = salary_data.get("max") if salary_data else None

            employment_type = item.get("type", "Full-Time")

            job = Job(
                title=title,
                company=company,
                location=location,
                url=item.get("url", ""),
                source=self.name,
                category=matched_category,
                posted_date=item.get("created_at", datetime.utcnow().isoformat()),
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
