"""
Glassdoor Scraper Agent — uses cloudscraper to bypass Cloudflare.
No API key required.
"""
import asyncio
import logging
import re
import json
from datetime import datetime, timezone
from typing import List
from concurrent.futures import ThreadPoolExecutor

import cloudscraper
from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

GLASSDOOR_BASE = "https://www.glassdoor.com/Job/jobs.htm"

_executor = ThreadPoolExecutor(max_workers=3)


def _scrape_glassdoor(keyword: str) -> str:
    """Sync Glassdoor scrape using cloudscraper."""
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "darwin", "mobile": False}
    )
    params = {
        "sc.keyword": keyword,
        "locT": "N",
        "locId": "1",
        "fromAge": "1",
        "sortBy": "date_desc",
    }
    try:
        resp = scraper.get(GLASSDOOR_BASE, params=params, timeout=20)
        if resp.status_code == 200:
            return resp.text
        logger.debug(f"[glassdoor] HTTP {resp.status_code} for '{keyword}'")
        return ""
    except Exception as e:
        logger.error(f"[glassdoor] Scrape error for '{keyword}': {e}")
        return ""


class GlassdoorAgent(BaseAgent):
    """Scrapes Glassdoor via cloudscraper."""

    name = "glassdoor"

    def is_configured(self) -> bool:
        return True

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Glassdoor for jobs."""
        jobs = []

        loop = asyncio.get_event_loop()
        html = await loop.run_in_executor(_executor, _scrape_glassdoor, keyword)

        if not html:
            return jobs

        # Try embedded JSON extraction
        json_patterns = [
            r'window\.__INITIAL_DATA__\s*=\s*({.+?});\s*</script>',
            r'"jobListings"\s*:\s*(\[.+?\])',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    raw = json.loads(match.group(1))
                    listings = raw if isinstance(raw, list) else raw.get("jobListings", raw.get("results", []))
                    for item in listings:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("jobTitle", item.get("title", ""))
                        company = ""
                        employer = item.get("employer", item.get("company", ""))
                        if isinstance(employer, dict):
                            company = employer.get("name", "")
                        else:
                            company = str(employer) if employer else ""
                        location_str = item.get("locationName", item.get("location", ""))
                        url = item.get("jobLink", item.get("url", ""))
                        if url and not url.startswith("http"):
                            url = f"https://www.glassdoor.com{url}"
                        is_remote = "remote" in str(location_str).lower()
                        job_type = "remote" if is_remote else "corporate"

                        if title:
                            job = Job(
                                title=title,
                                company=company or "Unknown",
                                location=str(location_str) or "United States",
                                url=url,
                                source="glassdoor",
                                category=category,
                                posted_date=datetime.now(timezone.utc).isoformat(),
                                job_type=job_type,
                                remote=is_remote,
                                search_keyword=keyword,
                            )
                            jobs.append(job)
                except (json.JSONDecodeError, TypeError):
                    pass

        # HTML fallback — extract from job cards
        if not jobs:
            titles = re.findall(r'class="[^"]*JobCard_jobTitle[^"]*"[^>]*>([^<]+)<', html)
            if not titles:
                titles = re.findall(r'<a[^>]*data-test="job-title"[^>]*>([^<]+)</a>', html)

            companies_raw = re.findall(r'class="[^"]*EmployerProfile[^"]*"[^>]*>([^<]+)<', html)
            if not companies_raw:
                companies_raw = re.findall(r'class="[^"]*JobCard_companyName[^"]*"[^>]*>([^<]+)<', html)

            locs = re.findall(r'class="[^"]*JobCard_location[^"]*"[^>]*>([^<]+)<', html)
            if not locs:
                locs = re.findall(r'<div[^>]*data-test="emp-location"[^>]*>([^<]+)</div>', html)

            urls_raw = re.findall(r'<a[^>]*data-test="job-title"[^>]*href="([^"]*)"', html)

            for i in range(len(titles)):
                title = titles[i].strip()
                company = companies_raw[i].strip() if i < len(companies_raw) else "Unknown"
                loc = locs[i].strip() if i < len(locs) else "United States"
                url = urls_raw[i] if i < len(urls_raw) else ""
                if url and not url.startswith("http"):
                    url = f"https://www.glassdoor.com{url}"
                is_remote = "remote" in loc.lower()

                job = Job(
                    title=title,
                    company=company,
                    location=loc,
                    url=url,
                    source="glassdoor",
                    category=category,
                    posted_date=datetime.now(timezone.utc).isoformat(),
                    job_type="remote" if is_remote else "corporate",
                    remote=is_remote,
                    search_keyword=keyword,
                )
                jobs.append(job)

        if jobs:
            logger.info(f"[glassdoor] Found {len(jobs)} jobs for '{keyword}' in {category}")

        await asyncio.sleep(2.5)
        return jobs

    async def search_all_categories(self) -> List[Job]:
        """Search with rate limiting."""
        all_jobs = []
        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[glassdoor] Searching category: {category}")
            for kw in keywords[:4]:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[glassdoor] Error searching '{kw}': {e}")
                await asyncio.sleep(1)
        logger.info(f"[glassdoor] Total jobs found: {len(all_jobs)}")
        return all_jobs
