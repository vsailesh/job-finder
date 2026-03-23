"""
USAJobs Agent — searches federal government job postings via the official API.
https://developer.usajobs.gov/API-Reference
Uses requests (sync) in a thread pool to avoid aiohttp header issues.
"""
import asyncio
import logging
import requests
from typing import List
from concurrent.futures import ThreadPoolExecutor

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _fetch_usajobs(keyword: str, api_key: str, email: str) -> dict:
    """Synchronous USAJobs API call using requests for reliable header handling."""
    headers = {
        "Authorization-Key": api_key,
        "User-Agent": email,
    }
    params = {
        "Keyword": keyword,
        "DatePosted": 1,
        "ResultsPerPage": 500,
        "Page": 1,
    }
    try:
        resp = requests.get(
            config.USAJOBS_BASE_URL,
            headers=headers,
            params=params,
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.error(f"[usajobs] HTTP {resp.status_code}: {resp.text[:200]}")
            return {}
    except Exception as e:
        logger.error(f"[usajobs] Request error: {e}")
        return {}


class USAJobsAgent(BaseAgent):
    """Searches the USAJobs API for federal government positions."""

    name = "usajobs"

    def is_configured(self) -> bool:
        return bool(config.USAJOBS_API_KEY and config.USAJOBS_EMAIL)

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search USAJobs for a specific keyword."""
        jobs = []

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            _executor,
            _fetch_usajobs,
            keyword,
            config.USAJOBS_API_KEY,
            config.USAJOBS_EMAIL,
        )

        if not data:
            return jobs

        search_result = data.get("SearchResult", {})
        count = int(search_result.get("SearchResultCount", 0))

        if count == 0:
            return jobs

        items = search_result.get("SearchResultItems", [])

        for item in items:
            matched = item.get("MatchedObjectDescriptor", {})
            position = matched.get("PositionTitle", "Unknown")
            org = matched.get("OrganizationName", "Unknown")
            url = matched.get("PositionURI", "")
            apply_url = matched.get("ApplyURI", [""])[0] if matched.get("ApplyURI") else url

            # Location
            locations = matched.get("PositionLocation", [])
            location_str = ", ".join(
                loc.get("LocationName", "") for loc in locations[:3]
            )
            if len(locations) > 3:
                location_str += f" +{len(locations) - 3} more"

            # Salary
            salary_min = None
            salary_max = None
            remuneration = matched.get("PositionRemuneration", [])
            if remuneration:
                try:
                    salary_min = float(remuneration[0].get("MinimumRange", 0))
                    salary_max = float(remuneration[0].get("MaximumRange", 0))
                except (ValueError, TypeError, IndexError):
                    pass

            # Description
            desc = matched.get("UserArea", {}).get("Details", {}).get("MajorDuties", "")
            if isinstance(desc, list):
                desc = " ".join(desc)
            if not desc:
                desc = matched.get("QualificationSummary", "")

            # Post date
            pub_date = matched.get("PublicationStartDate", "")

            # Employment type
            schedule = matched.get("PositionSchedule", [])
            emp_type = schedule[0].get("Name", "Full-Time") if schedule else "Full-Time"

            job = Job(
                title=position,
                company=org,
                location=location_str or "Various Locations",
                url=apply_url or url,
                source="usajobs",
                category=category,
                posted_date=pub_date,
                description=desc[:2000] if desc else "",
                salary_min=salary_min if salary_min else None,
                salary_max=salary_max if salary_max else None,
                job_type="federal",
                employment_type=emp_type,
                search_keyword=keyword,
            )
            jobs.append(job)

        if jobs:
            logger.info(
                f"[usajobs] Found {len(jobs)} jobs for '{keyword}' in {category}"
            )
        return jobs
