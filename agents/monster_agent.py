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
        """Launch headless Chrome and fetch Monster search results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[monster] playwright not installed")
            return ""

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = await context.new_page()

                url = f"{MONSTER_URL}?q={keyword}&where=United+States&page=1&recency=last+24+hours"
                await page.goto(url, wait_until="networkidle", timeout=30000)

                # Wait for job cards
                try:
                    await page.wait_for_selector('[data-testid="jobTitle"]', timeout=8000)
                except Exception:
                    try:
                        await page.wait_for_selector('.job-search-resultsstyle', timeout=5000)
                    except Exception:
                        await asyncio.sleep(3)

                html = await page.content()
                await browser.close()
                return html
        except Exception as e:
            logger.error(f"[monster] Playwright error for '{keyword}': {e}")
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
