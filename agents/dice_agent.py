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
                with open("/tmp/dice.html", "w") as f:
                    f.write(html)
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

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            job_cards = soup.find_all("div", {"data-testid": "job-card"})
            
            for card in job_cards:
                title_el = card.find("a", {"data-testid": "job-search-job-detail-link"})
                if not title_el:
                    continue
                    
                title = title_el.get_text(strip=True)
                url = title_el.get("href", "")
                
                company = "Unknown"
                company_el = card.select_one('a[href*="/company-profile/"]')
                if company_el:
                    company = company_el.get_text(strip=True)

                loc = "United States"
                p_tags = card.find_all("p", class_=lambda c: c and "text-zinc-600" in c)
                if p_tags:
                    loc = p_tags[0].get_text(strip=True)

                if url.startswith('/'):
                    url = f"https://www.dice.com{url}"
                else:
                    url = url.split("?")[0] if "?" in url and "jobId" not in url else url

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
        except Exception as e:
            logger.error(f"[dice] Error parsing HTML: {e}")

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
            for kw in keywords:
                try:
                    result = await self.search(kw, category)
                    if result:
                        all_jobs.extend(result)
                except Exception as e:
                    logger.error(f"[dice] Error searching '{kw}': {e}")
                # Use a lightweight delay between massive Playwright loads
                await asyncio.sleep(2)
                
        logger.info(f"[dice] Total jobs found: {len(all_jobs)}")
        return all_jobs
