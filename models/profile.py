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
        """
        Score how well this profile matches a job (0.0 - 1.0).

        Enhanced with weighted scoring across multiple factors:
        - Skills overlap (weighted most heavily)
        - Title similarity (using fuzzy matching)
        - Salary match
        - Category match
        - Location preference
        - Security clearance match
        """
        import config

        score = 0.0
        weights = config.MATCHING_WEIGHTS

        # 1. Skills match (highest weight)
        if self.skills:
            skills_score = self._score_skills(job_dict)
            score += skills_score * weights.get("skills", 0.35)

        # 2. Title similarity
        title_score = self._score_title_similarity(job_dict)
        score += title_score * weights.get("title", 0.25)

        # 3. Salary match
        salary_score = self._score_salary(job_dict)
        score += salary_score * weights.get("salary", 0.15)

        # 4. Category match
        if self.preferred_categories:
            if job_dict.get("category") in self.preferred_categories:
                score += 1.0 * weights.get("category", 0.10)

        # 5. Location preference
        location_score = self._score_location(job_dict)
        score += location_score * weights.get("location", 0.10)

        # 6. Security clearance match
        if self.security_clearance and self.security_clearance != "none":
            clearance_score = self._score_clearance(job_dict)
            score += clearance_score * weights.get("clearance", 0.05)

        return min(score, 1.0)

    def _score_skills(self, job_dict: dict) -> float:
        """
        Score skills overlap using fuzzy matching.

        Returns a score from 0.0 to 1.0 based on how many skills match.
        """
        if not self.skills:
            return 0.0

        title = job_dict.get("title", "").lower()
        desc = job_dict.get("description", "").lower()
        combined = f"{title} {desc}"

        matches = 0
        for skill in self.skills:
            skill_lower = skill.lower()
            # Exact match
            if skill_lower in combined:
                matches += 1
            else:
                # Try fuzzy matching if rapidfuzz is available
                try:
                    from rapidfuzz import fuzz
                    # Check for partial matches in the combined text
                    words = combined.split()
                    for word in words:
                        if fuzz.ratio(skill_lower, word) >= 85:
                            matches += 0.5
                            break
                except ImportError:
                    pass

        return min(matches / len(self.skills), 1.0)

    def _score_title_similarity(self, job_dict: dict) -> float:
        """
        Score title similarity using fuzzy matching.

        Compares the job title with the user's skills and experience level.
        """
        job_title = job_dict.get("title", "").lower()

        # Check for seniority match
        seniority_score = 1.0
        if self.years_experience >= 5 and not any(
            w in job_title for w in ["senior", "sr.", "lead", "principal", "staff", "manager"]
        ):
            seniority_score = 0.7  # Slight penalty for senior person on junior role
        elif self.years_experience < 3 and any(
            w in job_title for w in ["senior", "sr.", "lead", "principal", "director", "vp"]
        ):
            seniority_score = 0.5  # Penalty for junior person on senior role

        # Check for skill keywords in title
        title_skill_match = 0.0
        for skill in self.skills[:5]:  # Check top 5 skills
            if skill.lower() in job_title:
                title_skill_match += 0.2

        return min(seniority_score * (0.5 + title_skill_match), 1.0)

    def _score_salary(self, job_dict: dict) -> float:
        """
        Score salary match.

        Returns 1.0 if salary meets or exceeds target, partial score otherwise.
        """
        if not self.target_salary_min:
            return 1.0  # No preference, full score

        job_salary = job_dict.get("salary_min") or job_dict.get("salary_max")

        if not job_salary:
            return 0.5  # Salary unknown, neutral score

        if job_salary >= self.target_salary_min:
            return 1.0  # Meets or exceeds target

        # Partial score if close (within 20%)
        ratio = job_salary / self.target_salary_min
        if ratio >= 0.8:
            return 0.7
        elif ratio >= 0.6:
            return 0.4
        else:
            return 0.1

    def _score_location(self, job_dict: dict) -> float:
        """
        Score location match.

        Returns 1.0 for remote if preferred, or score based on location preference.
        """
        job_location = job_dict.get("location", "").lower()
        is_remote = job_dict.get("remote", False) or "remote" in job_location

        # If user prefers remote
        if self.location_preference and "remote" in self.location_preference.lower():
            if is_remote:
                return 1.0
            elif self.willing_to_relocate:
                return 0.6  # Willing to relocate, but prefers remote
            else:
                return 0.2

        # If user has specific location preference
        if self.location_preference and not is_remote:
            if self.location_preference.lower() in job_location:
                return 1.0
            elif self.willing_to_relocate:
                return 0.5
            else:
                return 0.1

        # No strong preference
        return 0.7

    def _score_clearance(self, job_dict: dict) -> float:
        """
        Score security clearance match.

        Returns 1.0 if user's clearance meets or exceeds job requirements.
        """
        desc = job_dict.get("description", "").lower()
        title = job_dict.get("title", "").lower()
        combined = f"{title} {desc}"

        # Check if job requires clearance
        clearance_levels = {
            "sci": 4,
            "top_secret": 3,
            "secret": 2,
            "confidential": 1,
            "none": 0,
        }

        user_level = clearance_levels.get(self.security_clearance.lower(), 0)

        # Determine required clearance level from job
        required_level = 0
        if "sci" in combined or "sensitive compartmented information" in combined:
            required_level = 4
        elif "top secret" in combined or "ts/" in combined or "ts clearance" in combined:
            required_level = 3
        elif "secret" in combined and "top secret" not in combined:
            required_level = 2
        elif "confidential" in combined:
            required_level = 1

        # If no clearance required, full score
        if required_level == 0:
            return 1.0

        # If user meets or exceeds required level
        if user_level >= required_level:
            return 1.0
        else:
            return 0.0  # Doesn't meet clearance requirement

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
