"""
State Government Agent — fetches jobs from state government portals.

Specializes in MD, VA, and DC government jobs.
Uses web scraping with cloudscraper.
"""
import logging
from typing import List
from datetime import datetime
import re
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class StateGovernmentAgent(BaseAgent):
    """Fetches jobs from state government portals."""

    name = "state_government"

    def __init__(self):
        super().__init__()
        try:
            import cloudscraper
            self.scraper = cloudscraper.create_scraper()
        except ImportError:
            logger.warning(f"[{self.name}] cloudscraper not installed, using requests")
            import requests
            self.scraper = requests

        # State portal configurations
        self.state_portals = {
            "maryland": {
                "name": "State of Maryland",
                "url": "https://www.jobapscloud.com/MD/",
                "search_url": "https://www.jobapscloud.com/MD/sup/listsalt.nsf/0b7b6a0e0f9e9b5485257a05006f39b3?SearchView&Query=",
            },
            "virginia": {
                "name": "Commonwealth of Virginia",
                "url": "https://virginiajobs.peopleadmin.com/",
                "search_url": "https://virginiajobs.peopleadmin.com/postings/search?utf8=%E2%9C%93&query=",
            },
            "dc": {
                "name": "District of Columbia Government",
                "url": "https://careers.dc.gov/",
                "search_url": "https://careers.dc.gov/jobs/",
            },
        }

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword."""
        jobs = []

        # Search each state portal
        for state_key, state_config in self.state_portals.items():
            try:
                state_jobs = await self._search_state_portal(state_key, state_config, keyword, category)
                jobs.extend(state_jobs)
            except Exception as e:
                logger.error(f"[{self.name}] Error searching {state_key}: {e}")
                continue

        logger.info(f"[{self.name}] Found {len(jobs)} jobs for '{keyword}'")
        return jobs

    async def _search_state_portal(self, state_key: str, state_config: dict, keyword: str, category: str) -> List[Job]:
        """Search a specific state portal."""
        jobs = []

        import asyncio

        # Maryland-specific scraping
        if state_key == "maryland":
            url = f"{state_config['search_url']}{keyword}"
            try:
                response = await asyncio.to_thread(
                    self.scraper.get,
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=30
                )

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")

                    # Maryland JobAPS uses tables
                    table = soup.find("table", class_="list")
                    if table:
                        rows = table.find_all("tr")[1:]  # Skip header
                        for row in rows:
                            cells = row.find_all("td")
                            if len(cells) >= 3:
                                title = cells[0].get_text(strip=True)
                                url_elem = cells[0].find("a")
                                url = url_elem.get("href", "") if url_elem else ""

                                if url and not url.startswith("http"):
                                    url = f"{state_config['url']}{url}"

                                # Extract job details
                                location = cells[1].get_text(strip=True) if len(cells) > 1 else "Maryland"
                                posted_date = cells[2].get_text(strip=True) if len(cells) > 2 else datetime.utcnow().isoformat()

                                # Extract salary
                                salary_text = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                                salary_min, salary_max = self._extract_salary(salary_text)

                                if title:
                                    job = Job(
                                        title=title,
                                        company=state_config["name"],
                                        location=location,
                                        url=url,
                                        source=self.name,
                                        category=category,
                                        posted_date=posted_date,
                                        description="",
                                        salary_min=salary_min,
                                        salary_max=salary_max,
                                        job_type="state",
                                        employment_type="Full-Time",
                                        remote=False,
                                        search_keyword=keyword,
                                    )
                                    jobs.append(job)

            except Exception as e:
                logger.debug(f"[{self.name}] Maryland scraping error: {e}")

        # Virginia-specific scraping (PeopleAdmin)
        elif state_key == "virginia":
            url = f"{state_config['url']}postings"
            params = {"query": keyword}

            try:
                response = await asyncio.to_thread(
                    self.scraper.get,
                    url,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=30
                )

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")

                    # PeopleAdmin uses specific classes
                    job_cards = soup.find_all("li", class_="posting") or soup.find_all("div", class_="posting")

                    for card in job_cards:
                        title_elem = card.find("h5") or card.find("h3") or card.find("a")
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link_elem = card.find("a", href=True)
                            url = link_elem.get("href", "") if link_elem else ""

                            if url and not url.startswith("http"):
                                url = f"{state_config['url']}{url}"

                            # Location
                            dept_elem = card.find("span", class_="department")
                            location = dept_elem.get_text(strip=True) if dept_elem else "Virginia"

                            # Posted date
                            date_elem = card.find("time")
                            posted_date = date_elem.get("datetime", "") if date_elem else datetime.utcnow().isoformat()

                            if title:
                                job = Job(
                                    title=title,
                                    company=state_config["name"],
                                    location=location,
                                    url=url,
                                    source=self.name,
                                    category=category,
                                    posted_date=posted_date,
                                    description="",
                                    job_type="state",
                                    employment_type="Full-Time",
                                    remote=False,
                                    search_keyword=keyword,
                                )
                                jobs.append(job)

            except Exception as e:
                logger.debug(f"[{self.name}] Virginia scraping error: {e}")

        # DC-specific scraping
        elif state_key == "dc":
            url = f"{state_config['url']}jobs?q={keyword}"

            try:
                response = await asyncio.to_thread(
                    self.scraper.get,
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=30
                )

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")

                    # DC uses specific job listing format
                    job_cards = soup.find_all("div", class_="job-item") or soup.find_all("tr", class_="data-row")

                    for card in job_cards:
                        title_elem = card.find("h3") or card.find("td", class_="job-title")
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link_elem = card.find("a", href=True)
                            url = link_elem.get("href", "") if link_elem else ""

                            if url and not url.startswith("http"):
                                url = f"{state_config['url']}{url}"

                            # Location
                            loc_elem = card.find("span", class_="location") or card.find("td", class_="location")
                            location = loc_elem.get_text(strip=True) if loc_elem else "Washington DC"

                            if title:
                                job = Job(
                                    title=title,
                                    company=state_config["name"],
                                    location=location,
                                    url=url,
                                    source=self.name,
                                    category=category,
                                    posted_date=datetime.utcnow().isoformat(),
                                    description="",
                                    job_type="state",
                                    employment_type="Full-Time",
                                    remote=False,
                                    search_keyword=keyword,
                                )
                                jobs.append(job)

            except Exception as e:
                logger.debug(f"[{self.name}] DC scraping error: {e}")

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
        """Override: Only search State Government category."""
        all_jobs = []

        # Get state government keywords
        state_keywords = config.SEARCH_CATEGORIES.get("State Government (DMV)", [])

        for keyword in state_keywords:
            jobs = await self.search(keyword, "State Government (DMV)")
            all_jobs.extend(jobs)

        logger.info(f"[{self.name}] Total jobs found: {len(all_jobs)}")
        return all_jobs
