"""
Profile model — represents a user profile for job applications.
Profiles are stored as JSON files in the profiles/ directory.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

PROFILES_DIR = Path(__file__).parent.parent / "profiles"


@dataclass
class Profile:
    """Represents a job applicant profile."""
    name: str  # Profile identifier, e.g. "Senior Engineer"
    full_name: str = ""
    email: str = ""
    phone: str = ""
    resume_path: str = ""  # Path to resume PDF
    cover_letter_template: str = ""  # Template with {job_title}, {company}, {skills} placeholders
    skills: List[str] = field(default_factory=list)
    preferred_categories: List[str] = field(default_factory=list)
    preferred_job_types: List[str] = field(default_factory=list)
    target_salary_min: Optional[float] = None
    target_salary_max: Optional[float] = None
    years_experience: int = 0
    security_clearance: str = ""  # none, secret, top_secret, sci
    education: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    location_preference: str = ""  # e.g. "Remote", "Washington DC", "Anywhere"
    willing_to_relocate: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def save(self) -> Path:
        """Save profile to JSON file."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = self.name.lower().replace(" ", "_").replace("/", "_")
        path = PROFILES_DIR / f"{safe_name}.json"
        self.updated_at = datetime.utcnow().isoformat()
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
        return path

    def render_cover_letter(self, job_title: str, company: str, description: str = "") -> str:
        """Render cover letter from template."""
        if not self.cover_letter_template:
            return self._default_cover_letter(job_title, company)

        skills_str = ", ".join(self.skills[:10])
        return self.cover_letter_template.format(
            full_name=self.full_name,
            job_title=job_title,
            company=company,
            skills=skills_str,
            years_experience=self.years_experience,
            education=self.education,
            email=self.email,
            phone=self.phone,
        )

    def _default_cover_letter(self, job_title: str, company: str) -> str:
        """Generate a basic cover letter."""
        skills_str = ", ".join(self.skills[:8])
        return f"""Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company}. With {self.years_experience} years of professional experience and expertise in {skills_str}, I am confident in my ability to contribute meaningfully to your team.

{f"My educational background includes {self.education}. " if self.education else ""}I am passionate about delivering high-quality results and continuously growing my skill set.

I would welcome the opportunity to discuss how my experience and skills align with your team's needs. Thank you for your consideration.

Best regards,
{self.full_name}
{self.email}
{self.phone}"""

    def matches_job(self, job_dict: dict) -> float:
        """Score how well this profile matches a job (0.0 - 1.0)."""
        score = 0.0
        total_factors = 0

        # Category match
        if self.preferred_categories:
            total_factors += 1
            if job_dict.get("category") in self.preferred_categories:
                score += 1.0

        # Job type match
        if self.preferred_job_types:
            total_factors += 1
            if job_dict.get("job_type") in self.preferred_job_types:
                score += 1.0

        # Salary match
        if self.target_salary_min and job_dict.get("salary_min"):
            total_factors += 1
            if job_dict["salary_min"] >= self.target_salary_min:
                score += 1.0
            elif job_dict["salary_min"] >= self.target_salary_min * 0.8:
                score += 0.5

        # Skills overlap (fuzzy)
        if self.skills:
            total_factors += 1
            title = job_dict.get("title", "").lower()
            desc = job_dict.get("description", "").lower()
            combined = f"{title} {desc}"
            matches = sum(1 for s in self.skills if s.lower() in combined)
            if matches > 0:
                score += min(matches / max(len(self.skills), 1), 1.0)

        return score / max(total_factors, 1)

    @classmethod
    def load(cls, name: str) -> Optional["Profile"]:
        """Load a profile from JSON file."""
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        path = PROFILES_DIR / f"{safe_name}.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def list_all(cls) -> List["Profile"]:
        """List all saved profiles."""
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profiles = []
        for file in sorted(PROFILES_DIR.glob("*.json")):
            try:
                with open(file) as f:
                    data = json.load(f)
                profiles.append(cls(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return profiles

    @classmethod
    def delete(cls, name: str) -> bool:
        """Delete a profile."""
        safe_name = name.lower().replace(" ", "_").replace("/", "_")
        path = PROFILES_DIR / f"{safe_name}.json"
        if path.exists():
            path.unlink()
            return True
        return False
