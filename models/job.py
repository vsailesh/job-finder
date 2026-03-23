"""
Job data model — the canonical representation of a job posting.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
import hashlib
import json


@dataclass
class Job:
    """Represents a single job posting from any source."""
    title: str
    company: str
    location: str
    url: str
    source: str  # usajobs, jsearch, remotive, adzuna
    category: str  # Science & Technology, Defense & Military, etc.
    posted_date: str  # ISO 8601 string
    description: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    job_type: str = "corporate"  # federal, state, corporate, remote
    employment_type: str = ""  # full-time, part-time, contract, etc.
    seniority: str = ""  # entry, mid, senior, executive
    remote: bool = False
    search_keyword: str = ""  # the keyword that found this job
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    @property
    def unique_hash(self) -> str:
        """Generate a unique hash for deduplication."""
        raw = f"{self.title.lower().strip()}|{self.company.lower().strip()}|{self.url.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        d = asdict(self)
        d["unique_hash"] = self.unique_hash
        return d
    
    def __repr__(self) -> str:
        salary = ""
        if self.salary_min and self.salary_max:
            salary = f" ${self.salary_min:,.0f}-${self.salary_max:,.0f}"
        elif self.salary_min:
            salary = f" ${self.salary_min:,.0f}+"
        return f"Job({self.title} @ {self.company} [{self.source}/{self.job_type}]{salary})"
