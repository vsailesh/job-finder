"""
Careers Agent — fetches jobs directly from company career pages
via Greenhouse, Lever, and Ashby ATS APIs.

All three APIs are free and require no authentication.
"""
import json
import logging
import re
from pathlib import Path
from typing import List, Optional
from html import unescape

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class CareersAgent(BaseAgent):
    """Fetches jobs directly from company career pages using ATS APIs."""

    name = "careers"

    def __init__(self):
        super().__init__()
        self.tracked_companies = self._load_tracked_companies()
        # Build a flat set of keywords for matching
        self._all_keywords = set()
        for keywords in config.SEARCH_CATEGORIES.values():
            for kw in keywords:
                self._all_keywords.add(kw.lower())

    @staticmethod
    def _load_tracked_companies() -> list:
        """Load tracked companies from JSON config."""
        path = config.TRACKED_COMPANIES_PATH
        if not path.exists():
            logger.warning(f"[careers] Tracked companies file not found: {path}")
            return []
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[careers] Failed to load tracked companies: {e}")
            return []

    def _match_category(self, title: str, description: str = "") -> Optional[str]:
        """Match a job title/description to a search category."""
        text = f"{title} {description}".lower()
        for category, keywords in config.SEARCH_CATEGORIES.items():
            for kw in keywords:
                if kw.lower() in text:
                    return category
        return None

    def _match_keyword(self, title: str, description: str = "") -> str:
        """Find the best matching keyword for a job."""
        text = f"{title} {description}".lower()
        for kw in self._all_keywords:
            if kw in text:
                return kw
        return ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags and unescape entities."""
        if not html:
            return ""
        text = re.sub(r"<[^>]+>", " ", html)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:2000]

    @staticmethod
    def _extract_salary(text: str):
        """Try to extract salary range from text."""
        salary_min = None
        salary_max = None
        # Look for patterns like $120,000 - $180,000 or $120K-$180K
        patterns = [
            r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:k|K)\s*[-–—to]+\s*\$\s*([\d,]+(?:\.\d+)?)\s*(?:k|K)",
            r"\$\s*([\d,]+(?:\.\d+)?)\s*[-–—to]+\s*\$\s*([\d,]+(?:\.\d+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    low = float(match.group(1).replace(",", ""))
                    high = float(match.group(2).replace(",", ""))
                    # Normalize K values
                    if low < 1000:
                        low *= 1000
                    if high < 1000:
                        high *= 1000
                    if 20_000 <= low <= 1_000_000 and 20_000 <= high <= 2_000_000:
                        salary_min = low
                        salary_max = high
                        break
                except ValueError:
                    continue
        return salary_min, salary_max

    # ──────────────────────────────────────────────
    # Greenhouse API
    # ──────────────────────────────────────────────
    async def _fetch_greenhouse(self, company: dict) -> List[Job]:
        """Fetch jobs from Greenhouse boards API."""
        slug = company["slug"]
        name = company["name"]
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        params = {"content": "true"}  # Include job description

        data = await self._request("GET", url, params=params)
        if not data:
            return []

        jobs_data = data.get("jobs", [])
        jobs = []

        for item in jobs_data:
            title = item.get("title", "")
            # Get description from content field
            content = item.get("content", "")
            desc_text = self._strip_html(content)

            category = self._match_category(title, desc_text)
            if not category:
                continue  # Skip jobs that don't match any category

            keyword = self._match_keyword(title, desc_text)

            # Location
            location = item.get("location", {}).get("name", "Unknown")

            # Check for remote
            remote = "remote" in location.lower() or "remote" in title.lower()

            # Salary extraction from description
            salary_min, salary_max = self._extract_salary(desc_text)

            job = Job(
                title=title,
                company=name,
                location=location,
                url=item.get("absolute_url", ""),
                source="careers",
                category=category,
                posted_date=item.get("first_published", item.get("updated_at", "")),
                description=desc_text,
                salary_min=salary_min,
                salary_max=salary_max,
                job_type="corporate",
                employment_type="Full-Time",
                remote=remote,
                search_keyword=keyword,
            )
            jobs.append(job)

        return jobs

    # ──────────────────────────────────────────────
    # Lever API
    # ──────────────────────────────────────────────
    async def _fetch_lever(self, company: dict) -> List[Job]:
        """Fetch jobs from Lever postings API."""
        slug = company["slug"]
        name = company["name"]
        url = f"https://api.lever.co/v0/postings/{slug}"
        params = {"mode": "json"}

        data = await self._request("GET", url, params=params)
        if not data or not isinstance(data, list):
            return []

        jobs = []

        for item in data:
            title = item.get("text", "")
            desc_plain = item.get("descriptionPlain", "")
            additional = item.get("additionalPlain", "")
            full_desc = f"{desc_plain} {additional}"[:2000]

            category = self._match_category(title, full_desc)
            if not category:
                continue

            keyword = self._match_keyword(title, full_desc)

            # Location
            categories = item.get("categories", {})
            location = categories.get("location", "Unknown")
            commitment = categories.get("commitment", "Full-Time")
            team = categories.get("team", "")

            remote = "remote" in location.lower() or "remote" in title.lower()

            # Salary from additional text
            salary_min, salary_max = self._extract_salary(full_desc)

            job = Job(
                title=title,
                company=name,
                location=location,
                url=item.get("hostedUrl", item.get("applyUrl", "")),
                source="careers",
                category=category,
                posted_date=str(item.get("createdAt", "")),
                description=full_desc,
                salary_min=salary_min,
                salary_max=salary_max,
                job_type="corporate",
                employment_type=commitment if commitment else "Full-Time",
                remote=remote,
                search_keyword=keyword,
            )
            jobs.append(job)

        return jobs

    # ──────────────────────────────────────────────
    # Ashby API
    # ──────────────────────────────────────────────
    async def _fetch_ashby(self, company: dict) -> List[Job]:
        """Fetch jobs from Ashby job board API."""
        slug = company["slug"]
        name = company["name"]
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"

        data = await self._request("GET", url)
        if not data:
            return []

        jobs_data = data.get("jobs", [])
        jobs = []

        for item in jobs_data:
            title = item.get("title", "")
            desc_html = item.get("descriptionHtml", "")
            desc_text = self._strip_html(desc_html)

            category = self._match_category(title, desc_text)
            if not category:
                continue

            keyword = self._match_keyword(title, desc_text)

            # Location
            location = item.get("location", "Unknown")
            remote = item.get("isRemote", False) or "remote" in location.lower()

            # Employment type
            emp_type_raw = item.get("employmentType", "FullTime")
            emp_map = {
                "FullTime": "Full-Time",
                "PartTime": "Part-Time",
                "Contract": "Contract",
                "Intern": "Internship",
                "Temporary": "Temporary",
            }
            employment_type = emp_map.get(emp_type_raw, emp_type_raw)

            # Salary
            salary_min, salary_max = self._extract_salary(desc_text)
            comp = item.get("compensation")
            if comp and not salary_min:
                try:
                    salary_min = comp.get("min", {}).get("value")
                    salary_max = comp.get("max", {}).get("value")
                except (AttributeError, TypeError):
                    pass

            job = Job(
                title=title,
                company=name,
                location=location,
                url=item.get("jobUrl", item.get("applyUrl", "")),
                source="careers",
                category=category,
                posted_date=item.get("publishedAt", ""),
                description=desc_text,
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                job_type="corporate",
                employment_type=employment_type,
                remote=remote,
                search_keyword=keyword,
            )
            jobs.append(job)

        return jobs

    # ──────────────────────────────────────────────
    # Workday API
    # ──────────────────────────────────────────────
    async def _fetch_workday(self, company: dict) -> List[Job]:
        """Fetch jobs from Workday cxs API."""
        slug = company["slug"] # e.g. "mastercard/CorporateCareers"
        name = company["name"]
        
        parts = slug.split("/")
        if len(parts) != 2:
            logger.error(f"[careers] Invalid Workday slug for {name}: {slug}")
            return []
            
        tenant, site = parts
        base_url = f"https://{tenant}.wd1.myworkdayjobs.com"
        api_base = f"{base_url}/wday/cxs/{tenant}/{site}"
        
        import requests
        import asyncio
        
        # 1. Fetch job list
        jobs_url = f"{api_base}/jobs"
        payload = {"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "Content-Type": "application/json",
            "Origin": f"https://{tenant}.wd1.myworkdayjobs.com",
            "Referer": f"https://{tenant}.wd1.myworkdayjobs.com/{site}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            resp = await asyncio.to_thread(requests.post, jobs_url, json=payload, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.error(f"[careers] Workday returned {resp.status_code}: {resp.text[:200]}")
                return []
            data = resp.json()
        except Exception as e:
            logger.error(f"[careers] Request failed for {jobs_url}: {e}")
            return []
            
        postings = data.get("jobPostings", [])
        if not postings:
            return []
            
        jobs = []
        
        # Helper to fetch individual job descriptions
        def fetch_desc_sync(job_path: str):
            detail_url = f"{api_base}{job_path}"
            return requests.get(detail_url, headers=headers, timeout=10)
            
        # 2. Fetch all descriptions concurrently
        sem = asyncio.Semaphore(5)
        
        async def fetch_with_sem(post):
            async with sem:
                resp = await asyncio.to_thread(fetch_desc_sync, post.get("externalPath", ""))
                if resp.status_code == 200:
                    return resp.json()
                return None
                
        details_results = await asyncio.gather(*[fetch_with_sem(p) for p in postings], return_exceptions=True)
        
        for post, detail in zip(postings, details_results):
            if isinstance(detail, Exception) or not detail:
                continue
                
            info = detail.get("jobPostingInfo", {})
            title = info.get("title", post.get("title", ""))
            desc_html = info.get("jobDescription", "")
            desc_text = self._strip_html(desc_html)
            
            category = self._match_category(title, desc_text)
            if not category:
                continue
                
            keyword = self._match_keyword(title, desc_text)
            
            # Location
            location = info.get("location", post.get("locationsText", "Unknown"))
            remote = "remote" in location.lower() or "remote" in title.lower()
            
            # Employment type
            emp_type = info.get("timeType", "Full time")
            if "full" in emp_type.lower():
                employment_type = "Full-Time"
            elif "part" in emp_type.lower():
                employment_type = "Part-Time"
            else:
                employment_type = emp_type
                
            # Salary
            salary_min, salary_max = self._extract_salary(desc_text)
            
            job = Job(
                title=title,
                company=name,
                location=location,
                url=f"{base_url}/en-US/{site}{post.get('externalPath', '')}",
                source="careers",
                category=category,
                posted_date=post.get("postedOn", ""),
                description=desc_text,
                salary_min=salary_min,
                salary_max=salary_max,
                job_type="corporate",
                employment_type=employment_type,
                remote=remote,
                search_keyword=keyword,
            )
            jobs.append(job)
            
        return jobs

    # ──────────────────────────────────────────────
    # Main search interface
    # ──────────────────────────────────────────────
    PLATFORM_HANDLERS = {
        "greenhouse": "_fetch_greenhouse",
        "lever": "_fetch_lever",
        "ashby": "_fetch_ashby",
        "workday": "_fetch_workday",
    }

    async def search(self, keyword: str, category: str) -> List[Job]:
        """Not used — this agent iterates companies, not keywords."""
        return []

    async def search_all_categories(self) -> List[Job]:
        """Override: fetch from all tracked companies instead of keyword search."""
        all_jobs = []

        if not self.tracked_companies:
            logger.warning("[careers] No tracked companies configured")
            return []

        for company in self.tracked_companies:
            platform = company.get("platform", "")
            handler_name = self.PLATFORM_HANDLERS.get(platform)

            if not handler_name:
                logger.warning(
                    f"[careers] Unknown platform '{platform}' for {company.get('name')}"
                )
                continue

            handler = getattr(self, handler_name)
            try:
                logger.info(
                    f"[careers] Fetching {company['name']} ({platform})..."
                )
                jobs = await handler(company)
                all_jobs.extend(jobs)
                logger.info(
                    f"[careers] {company['name']}: {len(jobs)} matching jobs"
                )
            except Exception as e:
                logger.error(
                    f"[careers] Error fetching {company.get('name')}: {e}",
                    exc_info=True,
                )

        logger.info(f"[careers] Total career-page jobs found: {len(all_jobs)}")
        return all_jobs
