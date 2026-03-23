"""
JSearch Agent — searches via RapidAPI's JSearch endpoint.
Aggregates results from LinkedIn, Indeed, Glassdoor, ZipRecruiter.
"""
import logging
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class JSearchAgent(BaseAgent):
    """Searches JSearch API for corporate job postings."""
    
    name = "jsearch"
    
    def is_configured(self) -> bool:
        # Requires both a RapidAPI key AND explicit JSearch subscription
        # Set JSEARCH_ENABLED=true in .env if you've subscribed to JSearch on RapidAPI
        import os
        return bool(config.RAPIDAPI_KEY and os.getenv("JSEARCH_ENABLED", "").lower() == "true")
    
    def _get_headers(self) -> dict:
        return {
            "X-RapidAPI-Key": config.RAPIDAPI_KEY,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }
    
    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search JSearch for a specific keyword."""
        jobs = []
        
        params = {
            "query": f"{keyword} in United States",
            "page": "1",
            "num_pages": "1",
            "date_posted": "today",
            "country": "us",
        }
        
        data = await self._request(
            "GET",
            config.JSEARCH_BASE_URL,
            headers=self._get_headers(),
            params=params,
        )
        
        if not data or data.get("status") != "OK":
            return jobs
        
        results = data.get("data", [])
        
        for item in results:
            # Determine job type
            employer_type = item.get("employer_company_type", "")
            job_type = "corporate"
            if employer_type and "government" in employer_type.lower():
                job_type = "federal"
            
            is_remote = item.get("job_is_remote", False)
            if is_remote:
                job_type = "remote"
            
            # Salary
            salary_min = item.get("job_min_salary")
            salary_max = item.get("job_max_salary")
            
            # Location
            city = item.get("job_city", "")
            state = item.get("job_state", "")
            country = item.get("job_country", "US")
            location = ", ".join(filter(None, [city, state, country]))
            if is_remote:
                location = f"Remote{f' - {location}' if location else ''}"
            
            # Employment type
            emp_type = item.get("job_employment_type", "")
            if emp_type:
                emp_type = emp_type.replace("FULLTIME", "Full-Time").replace(
                    "PARTTIME", "Part-Time"
                ).replace("CONTRACTOR", "Contract").replace("INTERN", "Internship")
            
            # Seniority
            seniority = ""
            req_exp = item.get("job_required_experience", {})
            if req_exp:
                level = req_exp.get("required_experience_in_months")
                if level:
                    try:
                        months = int(level)
                        if months <= 12:
                            seniority = "entry"
                        elif months <= 60:
                            seniority = "mid"
                        else:
                            seniority = "senior"
                    except (ValueError, TypeError):
                        pass
            
            job = Job(
                title=item.get("job_title", "Unknown"),
                company=item.get("employer_name", "Unknown"),
                location=location or "United States",
                url=item.get("job_apply_link", "") or item.get("job_google_link", ""),
                source="jsearch",
                category=category,
                posted_date=item.get("job_posted_at_datetime_utc", ""),
                description=(item.get("job_description", ""))[:2000],
                salary_min=float(salary_min) if salary_min else None,
                salary_max=float(salary_max) if salary_max else None,
                job_type=job_type,
                employment_type=emp_type,
                seniority=seniority,
                remote=is_remote or False,
                search_keyword=keyword,
            )
            jobs.append(job)
        
        if jobs:
            logger.info(
                f"[jsearch] Found {len(jobs)} jobs for '{keyword}' in {category}"
            )
        return jobs
