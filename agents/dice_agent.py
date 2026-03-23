import asyncio
import logging
import json
import re
import urllib.parse
from datetime import datetime, timezone
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)

class DiceAgent(BaseAgent):
    """Scrapes Dice.com using Playwright headless Chrome."""
    
    name = "dice"
    
    def is_configured(self) -> bool:
        return True

    async def _get_page_html(self, keyword: str) -> str:
        """Launch headless Chrome and fetch Dice search results."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[dice] playwright not installed")
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

                query = urllib.parse.quote(keyword)
                # Filter for jobs posted "Today" (last 24h)
                url = f"https://www.dice.com/jobs?q={query}&countryCode=US&radius=30&radiusUnit=mi&page=1&pageSize=100&language=en&postedDate=Today"
                
                logger.debug(f"[dice] Fetching {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=40000)
                
                # Wait for job cards to load
                try:
                    await page.wait_for_selector('a.card-title-link, [data-cy="card-title-link"]', timeout=10000)
                except Exception:
                    await asyncio.sleep(5)
                    
                html = await page.content()
                await browser.close()
                return html
        except Exception as e:
            logger.error(f"[dice] Playwright error for '{keyword}': {e}")
            return ""

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Dice for tech jobs via headless browser."""
        jobs = []
        html = await self._get_page_html(keyword)
        if not html:
            return jobs

        # Dice often changes its HTML structure, but typically uses `card-title-link` for the main job link.
        titles_and_urls = re.findall(r'<a[^>]*class="card-title-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        if not titles_and_urls:
            titles_and_urls = re.findall(r'<a[^>]*data-cy="card-title-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            
        companies = re.findall(r'<a[^>]*data-cy="search-result-company-name"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        locations = re.findall(r'<span[^>]*data-cy="search-result-location"[^>]*>(.*?)</span>', html, re.IGNORECASE | re.DOTALL)
        
        for i, (url, title_html) in enumerate(titles_and_urls):
            # Clean up title (remove inner HTML like spans/bold tags)
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            
            # Format URL
            if url.startswith('/'):
                url = f"https://www.dice.com{url}"
            else:
                # Dice sometimes uses relative or tracked URLs
                url = url.split("?")[0] if "?" in url and "jobId" not in url else url
                
            # Attempt to align company and location arrays with title arrays
            company = "Unknown"
            if i < len(companies):
                company = re.sub(r'<[^>]+>', '', companies[i]).strip()
                
            loc = "United States"
            if i < len(locations):
                loc = re.sub(r'<[^>]+>', '', locations[i]).strip()

            if title:
                is_remote = "remote" in loc.lower() or "remote" in title.lower()
                
                job = Job(
                    title=title,
                    company=company,
                    location=loc,
                    url=url,
                    source="dice",
                    category=category,
                    posted_date=datetime.now(timezone.utc).isoformat(),
                    job_type="remote" if is_remote else "corporate",
                    remote=is_remote,
                    search_keyword=keyword,
                )
                jobs.append(job)

        unique_jobs = list({j.url: j for j in jobs}.values())
        
        if unique_jobs:
            logger.info(f"[dice] Found {len(unique_jobs)} jobs for '{keyword}' in {category}")

        return unique_jobs

    async def search_all_categories(self) -> List[Job]:
        """Search with rate limiting."""
        all_jobs = []
        # Dice is highly IT-focused. Focus only on relevant categories to save scraping time.
        tech_categories = ["Science & Technology", "Finance", "Aerospace & Drones", "Defense & Military"]
        
        for category, keywords in config.SEARCH_CATEGORIES.items():
            if category not in tech_categories:
                continue
                
            logger.info(f"[dice] Searching category: {category}")
            for kw in keywords[:4]:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[dice] Error searching '{kw}': {e}")
                await asyncio.sleep(2)
        logger.info(f"[dice] Total jobs found: {len(all_jobs)}")
        return all_jobs
