"""
Indeed Scraper Agent — uses Playwright headless Chrome to bypass
Cloudflare and captcha challenges. No API key required.
"""
import asyncio
import logging
import re
import json
from datetime import datetime, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

INDEED_BASE = "https://www.indeed.com/jobs"


class IndeedScraperAgent(BaseAgent):
    """Scrapes Indeed using Playwright headless Chrome."""

    name = "indeed"

    def is_configured(self) -> bool:
        return True

    async def _get_page_html(self, keyword: str) -> str:
        """Launch headless Chrome and fetch Indeed search results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[indeed] playwright not installed")
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

                url = f"{INDEED_BASE}?q={keyword}&l=United+States&fromage=1&sort=date&limit=50"
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Wait for job cards to appear
                try:
                    await page.wait_for_selector('[class*="job_seen"]', timeout=8000)
                except Exception:
                    try:
                        await page.wait_for_selector('[class*="jobTitle"]', timeout=5000)
                    except Exception:
                        await asyncio.sleep(3)

                html = await page.content()
                await browser.close()
                return html
        except Exception as e:
            logger.error(f"[indeed] Playwright error for '{keyword}': {e}")
            return ""

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Indeed for jobs via headless browser."""
        jobs = []

        html = await self._get_page_html(keyword)
        if not html:
            return jobs

        # Method 1: Extract from mosaic provider JSON
        json_match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*({.+?});\s*</script>',
            html, re.DOTALL
        )
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                results = (
                    data.get("metaData", {})
                    .get("mosaicProviderJobCardsModel", {})
                    .get("results", [])
                )
                for item in results:
                    title = item.get("title", "")
                    company = item.get("company", "")
                    location_str = item.get("formattedLocation", "")
                    job_key = item.get("jobkey", "")
                    url = f"https://www.indeed.com/viewjob?jk={job_key}" if job_key else ""

                    salary_min = None
                    salary_max = None
                    sal = item.get("estimatedSalary", {})
                    if isinstance(sal, dict):
                        salary_min = sal.get("min")
                        salary_max = sal.get("max")

                    snippet = item.get("snippet", "")

                    job_type = "corporate"
                    gov_kw = ["government", "federal", "state of", "county", "city of",
                              "department of", "u.s.", "usda", "dod", "nasa"]
                    if any(gk in company.lower() for gk in gov_kw):
                        job_type = "federal"

                    is_remote = "remote" in location_str.lower() or \
                        bool(item.get("remoteWorkModel", {}).get("inlineText", "") == "Remote")
                    if is_remote:
                        job_type = "remote"

                    posted_date = item.get("pubDate", datetime.now(timezone.utc).isoformat())

                    job = Job(
                        title=title or "Unknown",
                        company=company or "Unknown",
                        location=location_str or "United States",
                        url=url,
                        source="indeed",
                        category=category,
                        posted_date=str(posted_date),
                        description=snippet[:2000] if snippet else "",
                        salary_min=float(salary_min) if salary_min else None,
                        salary_max=float(salary_max) if salary_max else None,
                        job_type=job_type,
                        remote=is_remote,
                        search_keyword=keyword,
                    )
                    jobs.append(job)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.debug(f"[indeed] JSON parse failed: {e}")

        # Method 2: HTML fallback
        if not jobs:
            titles = re.findall(
                r'<a[^>]*class="[^"]*jcs-JobTitle[^"]*"[^>]*href="([^"]*)"[^>]*>.*?<span[^>]*>([^<]+)</span>',
                html, re.DOTALL
            )
            companies = re.findall(
                r'<span[^>]*data-testid="company-name"[^>]*>([^<]+)</span>', html
            )
            locations_raw = re.findall(
                r'<div[^>]*data-testid="text-location"[^>]*>([^<]+)</div>', html
            )

            for i, (href, title) in enumerate(titles):
                company = companies[i].strip() if i < len(companies) else "Unknown"
                loc = locations_raw[i].strip() if i < len(locations_raw) else "United States"
                url = f"https://www.indeed.com{href}" if href.startswith("/") else href

                job_type = "corporate"
                if any(gk in company.lower() for gk in ["government", "federal", "state of"]):
                    job_type = "federal"
                if "remote" in loc.lower():
                    job_type = "remote"

                job = Job(
                    title=title.strip(),
                    company=company,
                    location=loc,
                    url=url,
                    source="indeed",
                    category=category,
                    posted_date=datetime.now(timezone.utc).isoformat(),
                    job_type=job_type,
                    remote="remote" in loc.lower(),
                    search_keyword=keyword,
                )
                jobs.append(job)

        if jobs:
            logger.info(f"[indeed] Found {len(jobs)} jobs for '{keyword}' in {category}")

        return jobs

    async def search_all_categories(self) -> List[Job]:
        """Search with rate limiting — slower due to browser overhead."""
        all_jobs = []
        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[indeed] Searching category: {category}")
            for kw in keywords[:4]:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[indeed] Error searching '{kw}': {e}")
                await asyncio.sleep(2)
        logger.info(f"[indeed] Total jobs found: {len(all_jobs)}")
        return all_jobs
