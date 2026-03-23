"""
RemoteOK Agent — searches the free RemoteOK API for remote jobs.
RemoteOK provides a public JSON API at https://remoteok.com/api
No API key required.
Note: Uses RemoteOK instead of remotejobs.io (which is paywalled).
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

# RemoteOK has a free public JSON API
REMOTEOK_URL = "https://remoteok.com/api"

HEADERS = {
    "User-Agent": "JobFinderAgent/1.0",
    "Accept": "application/json",
}


class RemoteOKAgent(BaseAgent):
    """Searches RemoteOK API for remote job postings (free, no key required)."""

    name = "remoteok"

    def is_configured(self) -> bool:
        return True  # No API key needed

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search RemoteOK for a specific keyword."""
        jobs = []

        try:
            async with self._semaphore:
                async with self.session.get(
                    REMOTEOK_URL,
                    headers=HEADERS,
                    timeout=config.REQUEST_TIMEOUT,
                ) as response:
                    if response.status != 200:
                        logger.debug(f"[remoteok] HTTP {response.status}")
                        return jobs
                    data = await response.json(content_type=None)
        except Exception as e:
            logger.error(f"[remoteok] Request failed: {e}")
            return jobs

        if not isinstance(data, list):
            return jobs

        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        keyword_lower = keyword.lower()

        for item in data:
            if not isinstance(item, dict):
                continue
            if "id" not in item:
                continue  # Skip header/metadata entries

            # Keyword match in title, company, description, or tags
            title = item.get("position", "")
            company = item.get("company", "")
            description = item.get("description", "")
            tags = " ".join(item.get("tags", []))
            searchable = f"{title} {company} {description} {tags}".lower()

            if keyword_lower not in searchable:
                continue

            # Date filter
            epoch = item.get("epoch")
            posted_date = ""
            if epoch:
                try:
                    post_dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                    if post_dt < cutoff:
                        continue
                    posted_date = post_dt.isoformat()
                except (ValueError, TypeError, OSError):
                    date_str = item.get("date", "")
                    posted_date = date_str

            # Location
            location = item.get("location", "")
            if not location:
                location = "Worldwide"
            location = f"Remote - {location}" if location != "Worldwide" else "Remote - Worldwide"

            # Salary
            salary_min = None
            salary_max = None
            salary_str = item.get("salary", "")
            if salary_str:
                nums = re.findall(r'[\d]+', str(salary_str).replace(",", ""))
                if len(nums) >= 2:
                    try:
                        salary_min = float(nums[0])
                        salary_max = float(nums[1])
                    except ValueError:
                        pass

            # Detect government jobs
            job_type = "remote"
            gov_kw = ["government", "federal", "state of", "department of"]
            if any(gk in company.lower() for gk in gov_kw):
                job_type = "federal"

            url = item.get("url", item.get("apply_url", ""))
            if item.get("slug"):
                url = url or f"https://remoteok.com/remote-jobs/{item['slug']}"

            job = Job(
                title=title or "Unknown",
                company=company or "Unknown",
                location=location,
                url=url,
                source="remoteok",
                category=category,
                posted_date=posted_date,
                description=(description or "")[:2000],
                salary_min=salary_min,
                salary_max=salary_max,
                job_type=job_type,
                remote=True,
                search_keyword=keyword,
            )
            jobs.append(job)

        if jobs:
            logger.info(f"[remoteok] Found {len(jobs)} jobs for '{keyword}' in {category}")
        return jobs

    async def search_all_categories(self) -> List[Job]:
        """
        RemoteOK API returns ALL jobs at once, so we fetch once
        and filter by all keywords across categories.
        """
        all_jobs = []

        # Fetch the full listing once
        try:
            async with self._semaphore:
                async with self.session.get(
                    REMOTEOK_URL,
                    headers=HEADERS,
                    timeout=config.REQUEST_TIMEOUT,
                ) as response:
                    if response.status != 200:
                        logger.error(f"[remoteok] HTTP {response.status}")
                        return all_jobs
                    data = await response.json(content_type=None)
        except Exception as e:
            logger.error(f"[remoteok] Fetch failed: {e}")
            return all_jobs

        if not isinstance(data, list):
            return all_jobs

        cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
        seen_ids = set()

        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[remoteok] Filtering category: {category}")

            for item in data:
                if not isinstance(item, dict) or "id" not in item:
                    continue

                item_id = item.get("id")
                if item_id in seen_ids:
                    continue

                # Date filter
                epoch = item.get("epoch")
                if epoch:
                    try:
                        post_dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                        if post_dt < cutoff:
                            continue
                    except (ValueError, TypeError, OSError):
                        continue

                # Keyword match
                title = item.get("position", "")
                company = item.get("company", "")
                description = item.get("description", "")
                tags = " ".join(item.get("tags", []))
                searchable = f"{title} {company} {description} {tags}".lower()

                matched_keyword = None
                for kw in keywords[:8]:
                    if kw.lower() in searchable:
                        matched_keyword = kw
                        break

                if not matched_keyword:
                    continue

                seen_ids.add(item_id)

                location = item.get("location", "Worldwide")
                location = f"Remote - {location}" if location else "Remote - Worldwide"

                salary_min = None
                salary_max = None
                salary_str = item.get("salary", "")
                if salary_str:
                    nums = re.findall(r'[\d]+', str(salary_str).replace(",", ""))
                    if len(nums) >= 2:
                        try:
                            salary_min = float(nums[0])
                            salary_max = float(nums[1])
                        except ValueError:
                            pass

                posted_date = ""
                if epoch:
                    try:
                        posted_date = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
                    except (ValueError, TypeError, OSError):
                        posted_date = item.get("date", "")

                url = item.get("url", item.get("apply_url", ""))
                if item.get("slug"):
                    url = url or f"https://remoteok.com/remote-jobs/{item['slug']}"

                job = Job(
                    title=title or "Unknown",
                    company=company or "Unknown",
                    location=location,
                    url=url,
                    source="remoteok",
                    category=category,
                    posted_date=posted_date,
                    description=(description or "")[:2000],
                    salary_min=salary_min,
                    salary_max=salary_max,
                    job_type="remote",
                    remote=True,
                    search_keyword=matched_keyword,
                )
                all_jobs.append(job)

        logger.info(f"[remoteok] Total jobs found: {len(all_jobs)}")
        return all_jobs
