"""
Health eCareers Agent — fetches healthcare and medical jobs.

Specializes in healthcare positions: physicians, nurses, allied health, and more.
Uses web scraping with cloudscraper.
"""
import logging
from typing import List
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class HealthECareersAgent(BaseAgent):
    """Fetches jobs from Health eCareers."""

    name = "health_ecareers"

    def __init__(self):
        super().__init__()
        # Import cloudscraper here to avoid issues if not installed
        try:
            import cloudscraper
            self.scraper = cloudscraper.create_scraper()
        except ImportError:
            logger.warning(f"[{self.name}] cloudscraper not installed, using requests")
            import requests
            self.scraper = requests

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword."""
        jobs = []

        # Health eCareers search URL
        base_url = config.HEALTH_ECAREERS_BASE_URL or "https://www.healthecareers.com"

        # Build search parameters
        search_params = {
            "q": keyword,
            "radius": 100,
            "sort": "date",
            "days": 1,  # Last 24 hours
        }

        # Make request using cloudscraper
        import asyncio

        try:
            response = await asyncio.to_thread(
                self.scraper.get,
                f"{base_url}/jobs",
                params=search_params,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"[{self.name}] HTTP {response.status_code}: {response.text[:200]}")
                return []

            soup = BeautifulSoup(response.text, "html.parser")

            # Find job cards (adjust selectors based on actual site structure)
            job_cards = soup.find_all("div", class_="job-listing") or soup.find_all("article", class_="job")

            for card in job_cards:
                try:
                    # Extract job details
                    title_elem = card.find("h3") or card.find("h2") or card.find("a", class_="job-title")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)

                    company_elem = card.find("span", class_="company") or card.find("div", class_="employer")
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"

                    if not title or not company:
                        continue

                    # Location
                    location_elem = card.find("span", class_="location") or card.find("div", class_="job-location")
                    location = location_elem.get_text(strip=True) if location_elem else "Unknown"

                    # URL
                    link_elem = card.find("a", href=True)
                    url = link_elem.get("href", "") if link_elem else ""
                    if url and not url.startswith("http"):
                        url = f"{base_url}{url}"

                    # Description
                    desc_elem = card.find("p", class_="description") or card.find("div", class_="job-summary")
                    description = desc_elem.get_text(strip=True)[:500] if desc_elem else ""

                    # Salary extraction
                    salary_min, salary_max = self._extract_salary(description)

                    # Employment type
                    employment_type = "Full-Time"
                    if "part" in description.lower() or "prn" in description.lower():
                        employment_type = "Part-Time"
                    elif "contract" in description.lower() or "travel" in description.lower():
                        employment_type = "Contract"

                    # Seniority
                    seniority = ""
                    title_lower = title.lower()
                    if any(w in title_lower for w in ["chief", "director", "lead", "supervisor"]):
                        seniority = "executive"
                    elif any(w in title_lower for w in ["senior", "sr."]):
                        seniority = "senior"
                    elif any(w in title_lower for w in ["entry", "junior", "jr."]):
                        seniority = "entry"

                    # Remote check
                    remote = "remote" in location.lower() or "telehealth" in description.lower()

                    # Posted date
                    posted_date = datetime.utcnow().isoformat()
                    date_elem = card.find("time") or card.find("span", class_="posted-date")
                    if date_elem:
                        posted_date = date_elem.get("datetime", "") or date_elem.get_text(strip=True)

                    job = Job(
                        title=title,
                        company=company,
                        location=location,
                        url=url,
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

                except Exception as e:
                    logger.debug(f"[{self.name}] Error parsing job card: {e}")
                    continue

        except Exception as e:
            logger.error(f"[{self.name}] Request failed: {e}")
            return []

        logger.info(f"[{self.name}] Found {len(jobs)} jobs for '{keyword}'")
        return jobs

    @staticmethod
    def _extract_salary(text: str):
        """Extract salary range from text."""
        salary_min = None
        salary_max = None

        patterns = [
            r'\$\s*([\d,]+)(?:\s*-\s*\$?\s*([\d,]+))?',
            r'([\d,]+)\s*-\s*([\d,]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    salary_min = float(match.group(1).replace(',', ''))
                    if match.group(2):
                        salary_max = float(match.group(2).replace(',', ''))

                    # Normalize K values
                    if salary_min < 1000:
                        salary_min *= 1000
                    if salary_max and salary_max < 1000:
                        salary_max *= 1000

                    if 20000 <= salary_min <= 1000000:
                        break
                except (ValueError, AttributeError):
                    continue

        return salary_min, salary_max

    async def search_all_categories(self) -> List[Job]:
        """Override: Focus on Healthcare category."""
        all_jobs = []

        # Only search healthcare keywords
        healthcare_keywords = config.SEARCH_CATEGORIES.get("Healthcare", [])

        for keyword in healthcare_keywords[:15]:  # Limit to top 15 keywords
            jobs = await self.search(keyword, "Healthcare")
            all_jobs.extend(jobs)

        logger.info(f"[{self.name}] Total jobs found: {len(all_jobs)}")
        return all_jobs
