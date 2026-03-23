"""
Adzuna Agent — searches the Adzuna job aggregator API.
Covers corporate and state-level job postings.
"""
import logging
from typing import List

from agents.base_agent import BaseAgent
from models.job import Job
import config

logger = logging.getLogger(__name__)


class AdzunaAgent(BaseAgent):
    """Searches Adzuna API for job postings across the US."""
    
    name = "adzuna"
    
    def is_configured(self) -> bool:
        return bool(config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY)
    
    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search Adzuna for a specific keyword."""
        jobs = []
        page = 1
        max_pages = 3  # Limit to avoid rate limits
        
        while page <= max_pages:
            url = f"{config.ADZUNA_BASE_URL}/{page}"
            params = {
                "app_id": config.ADZUNA_APP_ID,
                "app_key": config.ADZUNA_APP_KEY,
                "what": keyword,
                "max_days_old": 1,  # Last 24 hours
                "results_per_page": 50,
                "content-type": "application/json",
                "sort_by": "date",
            }
            
            data = await self._request("GET", url, params=params)
            
            if not data:
                break
            
            results = data.get("results", [])
            if not results:
                break
            
            for item in results:
                # Location
                loc = item.get("location", {})
                area = loc.get("area", [])
                location = ", ".join(area) if area else item.get("location", {}).get(
                    "display_name", "United States"
                )
                
                # Determine job type
                company_name = item.get("company", {}).get("display_name", "Unknown")
                job_type = "corporate"
                gov_keywords = [
                    "state of", "county of", "city of", "department of",
                    "government", "federal", "municipality", "public",
                ]
                if any(gk in company_name.lower() for gk in gov_keywords):
                    job_type = "state"
                
                # Salary
                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                
                # Employment type
                contract_type = item.get("contract_type", "")
                emp_type = "Full-Time"
                if contract_type:
                    emp_type_map = {
                        "permanent": "Full-Time",
                        "contract": "Contract",
                        "part_time": "Part-Time",
                    }
                    emp_type = emp_type_map.get(contract_type, contract_type.title())
                
                # Contract time
                contract_time = item.get("contract_time", "")
                if contract_time == "part_time":
                    emp_type = "Part-Time"
                
                job = Job(
                    title=item.get("title", "Unknown"),
                    company=company_name,
                    location=location,
                    url=item.get("redirect_url", ""),
                    source="adzuna",
                    category=category,
                    posted_date=item.get("created", ""),
                    description=(item.get("description", ""))[:2000],
                    salary_min=float(salary_min) if salary_min else None,
                    salary_max=float(salary_max) if salary_max else None,
                    job_type=job_type,
                    employment_type=emp_type,
                    search_keyword=keyword,
                )
                jobs.append(job)
            
            # Check if we have more pages
            total = data.get("count", 0)
            if page * 50 >= total:
                break
            page += 1
        
        if jobs:
            logger.info(
                f"[adzuna] Found {len(jobs)} jobs for '{keyword}' in {category}"
            )
        return jobs
