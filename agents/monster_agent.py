"""
Monster Scraper Agent — uses Playwright headless Chrome to bypass
Cloudflare JS challenge. No API key required.
"""
import asyncio
import logging
import json
import re
from datetime import datetime, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

MONSTER_URL = "https://www.monster.com/jobs/search"


class MonsterAgent(BaseAgent):
    """Scrapes Monster using Playwright headless Chrome."""

    name = "monster"

    def is_configured(self) -> bool:
        return True

    async def _get_page_html(self, keyword: str) -> str:
        """Fetch Monster search results via ScraperAPI."""
        import aiohttp
        import urllib.parse
        
        if not config.SCRAPERAPI_KEY:
            logger.error("[monster] SCRAPERAPI_KEY is not set. Monster requires ScraperAPI to bypass DataDome.")
            return ""

        target_url = f"{MONSTER_URL}?q={keyword}&where=United+States&page=1&recency=last+24+hours"
        encoded_url = urllib.parse.quote(target_url)
        
        # ScraperAPI requires render=true to execute Monster's React app
        api_url = f"http://api.scraperapi.com?api_key={config.SCRAPERAPI_KEY}&url={encoded_url}&render=true"
        
        logger.debug(f"[monster] Fetching via ScraperAPI: {target_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                # ScraperAPI can take up to 60 seconds to solve Captchas and render the page
                async with session.get(api_url, timeout=90) as response:
                    if response.status == 200:
                        html = await response.text()
                        if "captcha-delivery" in html or "DataDome" in html:
                            logger.error("[monster] ScraperAPI failed to bypass DataDome CAPTCHA.")
                            return ""
                        return html
                    else:
                        logger.error(f"[monster] ScraperAPI returned status {response.status}")
                        return ""
        except Exception as e:
            logger.error(f"[monster] ScraperAPI error for '{keyword}': {e}")
            return ""

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Monster for jobs via headless browser."""
        jobs = []

        html = await self._get_page_html(keyword)
        if not html:
            return jobs

        # Try __NEXT_DATA__ extraction
        json_patterns = [
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>\s*({.+?})\s*</script>',
            r'window\.__NEXT_DATA__\s*=\s*({.+?})\s*;?\s*</script>',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    props = data.get("props", {}).get("pageProps", {})
                    results = (
                        props.get("searchResults", {}).get("jobResults", [])
                        or props.get("jobs", [])
                        or props.get("initialData", {}).get("jobs", [])
                    )

                    for item in results:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("title", item.get("jobTitle", ""))
                        company_raw = item.get("companyName", item.get("company", ""))
                        if isinstance(company_raw, dict):
                            company = company_raw.get("name", "Unknown")
                        else:
                            company = str(company_raw) if company_raw else "Unknown"

                        location_str = item.get("location", item.get("jobLocation", ""))
                        if isinstance(location_str, dict):
                            location_str = f"{location_str.get('city', '')}, {location_str.get('state', '')}".strip(", ")

                        url = item.get("url", item.get("applyUrl", ""))
                        if url and not url.startswith("http"):
                            url = f"https://www.monster.com{url}"

                        posted_date = item.get("postedDate", item.get("datePosted", ""))
                        is_remote = "remote" in str(location_str).lower() or item.get("isRemote", False)
                        job_type = "remote" if is_remote else "corporate"

                        salary_min = None
                        salary_max = None
                        salary = item.get("salary", item.get("compensation", {}))
                        if isinstance(salary, dict):
                            salary_min = salary.get("min", salary.get("minimumValue"))
                            salary_max = salary.get("max", salary.get("maximumValue"))

                        if title:
                            job = Job(
                                title=title,
                                company=company,
                                location=str(location_str) or "United States",
                                url=url,
                                source="monster",
                                category=category,
                                posted_date=str(posted_date) if posted_date else datetime.now(timezone.utc).isoformat(),
                                salary_min=float(salary_min) if salary_min else None,
                                salary_max=float(salary_max) if salary_max else None,
                                job_type=job_type,
                                remote=is_remote,
                                search_keyword=keyword,
                            )
                            jobs.append(job)
                    if jobs:
                        break
                except (json.JSONDecodeError, TypeError):
                    pass

        # HTML fallback
        if not jobs:
            titles = re.findall(r'data-testid="jobTitle"[^>]*>([^<]+)<', html)
            companies_raw = re.findall(r'data-testid="company"[^>]*>([^<]+)<', html)
            locs = re.findall(r'data-testid="jobLocation"[^>]*>([^<]+)<', html)
            hrefs = re.findall(r'<a[^>]*data-testid="jobTitle"[^>]*href="([^"]*)"', html)

            for i in range(len(titles)):
                title = titles[i].strip()
                company = companies_raw[i].strip() if i < len(companies_raw) else "Unknown"
                loc = locs[i].strip() if i < len(locs) else "United States"
                url = hrefs[i] if i < len(hrefs) else ""
                if url and not url.startswith("http"):
                    url = f"https://www.monster.com{url}"

                job = Job(
                    title=title,
                    company=company,
                    location=loc,
                    url=url,
                    source="monster",
                    category=category,
                    posted_date=datetime.now(timezone.utc).isoformat(),
                    job_type="remote" if "remote" in loc.lower() else "corporate",
                    remote="remote" in loc.lower(),
                    search_keyword=keyword,
                )
                jobs.append(job)

        if jobs:
            logger.info(f"[monster] Found {len(jobs)} jobs for '{keyword}' in {category}")

        return jobs

    async def search_all_categories(self) -> List[Job]:
        """Search with rate limiting — slower due to browser overhead."""
        all_jobs = []
        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[monster] Searching category: {category}")
            for kw in keywords[:4]:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[monster] Error searching '{kw}': {e}")
                await asyncio.sleep(2)
        logger.info(f"[monster] Total jobs found: {len(all_jobs)}")
        return all_jobs
