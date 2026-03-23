"""
LinkedIn RSS Agent — scrapes LinkedIn's public job search pages.
No API key required. Uses public search with proper headers.
"""
import asyncio
import logging
import re
import json
from datetime import datetime, timedelta, timezone
from typing import List
from urllib.parse import quote_plus

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

LINKEDIN_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class LinkedInAgent(BaseAgent):
    """Scrapes LinkedIn's public (guest) job listings."""

    name = "linkedin"

    def is_configured(self) -> bool:
        return True  # No API key needed

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search LinkedIn public jobs for a specific keyword."""
        jobs = []

        # LinkedIn f_TPR=r86400 = past 24h
        params = {
            "keywords": keyword,
            "location": "United States",
            "f_TPR": "r86400",  # Past 24 hours
            "start": "0",
            "sortBy": "DD",  # Date descending
        }

        try:
            async with self._semaphore:
                async with self.session.get(
                    LINKEDIN_BASE,
                    params=params,
                    headers=HEADERS,
                    timeout=config.REQUEST_TIMEOUT,
                ) as response:
                    if response.status != 200:
                        logger.debug(f"[linkedin] HTTP {response.status} for '{keyword}'")
                        return jobs
                    html = await response.text()
        except Exception as e:
            logger.error(f"[linkedin] Request failed for '{keyword}': {e}")
            return jobs

        # Parse LinkedIn job cards from HTML
        # Each job card is in a <li> with base-card class
        card_pattern = re.compile(
            r'<div[^>]*class="[^"]*base-card[^"]*"[^>]*>(.+?)</div>\s*</li>',
            re.DOTALL
        )

        # Alternative: parse individual fields
        # Title
        title_pattern = re.compile(
            r'<h3[^>]*class="[^"]*base-search-card__title[^"]*"[^>]*>\s*([^<]+?)\s*</h3>'
        )
        # Company
        company_pattern = re.compile(
            r'<h4[^>]*class="[^"]*base-search-card__subtitle[^"]*"[^>]*>\s*<a[^>]*>\s*([^<]+?)\s*</a>'
        )
        # Location
        location_pattern = re.compile(
            r'<span[^>]*class="[^"]*job-search-card__location[^"]*"[^>]*>\s*([^<]+?)\s*</span>'
        )
        # URL
        url_pattern = re.compile(
            r'<a[^>]*class="[^"]*base-card__full-link[^"]*"[^>]*href="([^"]*)"'
        )
        # Date
        date_pattern = re.compile(
            r'<time[^>]*datetime="([^"]*)"'
        )

        titles = title_pattern.findall(html)
        companies = company_pattern.findall(html)
        locations = location_pattern.findall(html)
        urls = url_pattern.findall(html)
        dates = date_pattern.findall(html)

        count = min(len(titles), len(companies), len(urls))

        for i in range(count):
            title = titles[i].strip() if i < len(titles) else "Unknown"
            company = companies[i].strip() if i < len(companies) else "Unknown"
            location_str = locations[i].strip() if i < len(locations) else "United States"
            url = urls[i].strip() if i < len(urls) else ""
            posted_date = dates[i].strip() if i < len(dates) else datetime.now(timezone.utc).date().isoformat()

            # Clean URL (remove tracking params)
            if "?" in url:
                url = url.split("?")[0]

            # Detect job type
            job_type = "corporate"
            gov_keywords = ["government", "federal", "state of", "county", "city of",
                          "department of", "u.s.", "usda", "dod", "nasa", "army", "navy", "air force"]
            if any(gk in company.lower() for gk in gov_keywords):
                job_type = "federal"

            is_remote = "remote" in location_str.lower()
            if is_remote:
                job_type = "remote"

            job = Job(
                title=title,
                company=company,
                location=location_str,
                url=url,
                source="linkedin",
                category=category,
                posted_date=posted_date,
                job_type=job_type,
                remote=is_remote,
                search_keyword=keyword,
            )
            jobs.append(job)

        if jobs:
            logger.info(f"[linkedin] Found {len(jobs)} jobs for '{keyword}' in {category}")

        # Rate limiting
        await asyncio.sleep(1.5)
        return jobs

    async def search_all_categories(self) -> List[Job]:
        """Search with sequential rate limiting."""
        all_jobs = []

        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[linkedin] Searching category: {category}")

            # Use first 5 keywords per category
            for kw in keywords[:5]:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[linkedin] Error searching '{kw}': {e}")
                await asyncio.sleep(0.8)

        logger.info(f"[linkedin] Total jobs found: {len(all_jobs)}")
        return all_jobs
