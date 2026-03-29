"""
Central configuration for Job Finding Agent.
Loads API keys from .env and defines search categories/keywords.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# ─── Helper to get config from environment or Streamlit secrets ─────
def _get_config(key: str, default: str = "") -> str:
    """Get configuration value from environment or Streamlit secrets."""
    # 1. Try environment variables first (works locally and in GitHub Actions)
    value = os.getenv(key, "")
    if value:
        return value
    
    # 2. Try Streamlit secrets (works on Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except ImportError:
        pass
    except Exception:
        pass
    
    return default

# ─── API Keys ───────────────────────────────────────────────
USAJOBS_API_KEY = _get_config("USAJOBS_API_KEY")
USAJOBS_EMAIL = _get_config("USAJOBS_EMAIL")
RAPIDAPI_KEY = _get_config("RAPIDAPI_KEY")
ADZUNA_APP_ID = _get_config("ADZUNA_APP_ID")
ADZUNA_APP_KEY = _get_config("ADZUNA_APP_KEY")
SCRAPERAPI_KEY = _get_config("SCRAPERAPI_KEY")

# ─── Database ───────────────────────────────────────────────
DB_PATH = PROJECT_ROOT / "data" / "jobs.db"
TRACKED_COMPANIES_PATH = PROJECT_ROOT / "data" / "tracked_companies.json"

def get_database():
    """Factory to get Turso Cloud database instance (Turso is required)."""
    # Read at call time so Streamlit secrets are available (not at import time)
    turso_url = _get_config("TURSO_DATABASE_URL")
    turso_token = _get_config("TURSO_AUTH_TOKEN")
    
    if not turso_url or not turso_token:
        raise ValueError(
            "Turso Cloud database credentials are required. "
            "Set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in .env file or Streamlit secrets."
        )

    # Use HTTP-based Turso client (works on Streamlit Cloud without compilation)
    from models.turso_http_database import TursoHTTPDatabase
    return TursoHTTPDatabase(turso_url, turso_token)

# ─── API Endpoints ──────────────────────────────────────────
USAJOBS_BASE_URL = "https://data.usajobs.gov/api/Search"
JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"
REMOTIVE_BASE_URL = "https://remotive.com/api/remote-jobs"
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"

# ─── Search Categories & Keywords ───────────────────────────
SEARCH_CATEGORIES = {
    "Science & Technology": [
        "software engineer",
        "data scientist",
        "artificial intelligence",
        "machine learning engineer",
        "cybersecurity analyst",
        "cloud engineer",
        "devops engineer",
        "systems engineer",
        "network engineer",
        "data engineer",
        "full stack developer",
        "backend developer",
        "frontend developer",
        "information technology",
        "computer science",
        "research scientist",
    ],
    "Manufacturing": [
        "manufacturing engineer",
        "production engineer",
        "quality control engineer",
        "CNC machinist",
        "industrial engineer",
        "process engineer",
        "supply chain engineer",
        "operations manager manufacturing",
        "plant manager",
        "lean manufacturing",
    ],
    "Pharmacy & Biotech": [
        "pharmacist",
        "pharmaceutical scientist",
        "biotechnology",
        "clinical research associate",
        "drug development",
        "bioinformatics",
        "molecular biologist",
        "biochemist",
        "regulatory affairs pharmaceutical",
        "clinical trials manager",
        "biomedical engineer",
        "genomics",
    ],
    "Defense & Military": [
        "defense contractor",
        "intelligence analyst",
        "security clearance",
        "DoD",
        "military analyst",
        "defense systems engineer",
        "weapons systems",
        "signals intelligence",
        "counterintelligence",
        "defense program manager",
        "military operations",
        "combat systems",
    ],
    "Finance": [
        "financial analyst",
        "quantitative analyst",
        "fintech",
        "risk analyst",
        "investment banker",
        "portfolio manager",
        "financial engineer",
        "compliance analyst",
        "actuarial analyst",
        "blockchain developer",
        "trading systems",
        "financial technology",
    ],
    "Robotics & Automation": [
        "robotics engineer",
        "automation engineer",
        "mechatronics engineer",
        "control systems engineer",
        "robot programmer",
        "autonomous systems",
        "computer vision engineer",
        "embedded systems engineer",
        "PLC programmer",
        "industrial automation",
    ],
    "Nuclear": [
        "nuclear engineer",
        "reactor engineer",
        "radiation protection",
        "nuclear physicist",
        "health physicist",
        "nuclear safety",
        "nuclear operations",
        "reactor operator",
        "nuclear waste management",
        "criticality safety",
    ],
    "Aerospace & Drones": [
        "aerospace engineer",
        "avionics engineer",
        "satellite engineer",
        "UAV engineer",
        "drone operator",
        "propulsion engineer",
        "flight systems engineer",
        "spacecraft engineer",
        "orbital mechanics",
        "unmanned aerial systems",
        "flight test engineer",
        "aerodynamics engineer",
    ],
    "State Government (DMV)": [
        "State of Maryland",
        "Commonwealth of Virginia",
        "District of Columbia Government",
        "Maryland State jobs",
        "Virginia State jobs",
        "Washington DC Government",
    ],
    "Healthcare": [
        "registered nurse",
        "physician",
        "medical doctor",
        "surgeon",
        "nurse practitioner",
        "physician assistant",
        "medical technologist",
        "radiologist",
        "physical therapist",
        "occupational therapist",
        "health informatics",
        "hospital administrator",
        "medical device engineer",
        "clinical nurse specialist",
        "healthcare data analyst",
        "epidemiologist",
    ],
}

# Flattened list for quick access
ALL_KEYWORDS = []
for keywords in SEARCH_CATEGORIES.values():
    ALL_KEYWORDS.extend(keywords)

# ─── Agent Settings ─────────────────────────────────────────
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
CONCURRENT_REQUESTS = 5  # max concurrent API calls per agent

# ─── Source Configuration ─────────────────────────────────────
# Config-driven architecture: enable/disable sources dynamically
ENABLED_SOURCES = {
    # Original sources
    "usajobs": True,
    "jsearch": True,
    "remotive": True,
    "adzuna": True,
    "arbeitnow": True,
    "joinrise": True,
    "indeed": True,
    "linkedin": True,
    "glassdoor": True,
    "monster": True,
    "remoteok": True,
    "careers": True,
    "dice": True,
    # New sources (added in v2.0)
    "ziprecruiter": True,
    "yc_jobs": True,
    "otta": True,
    "clearancejobs": True,
    "health_ecareers": True,
    "state_government": True,
}

# ─── Additional API Endpoints ────────────────────────────────
ZIPRECRUITER_BASE_URL = "https://api.ziprecruiter.com/jobs-app/version"
ZIPRECRUITER_API_KEY = _get_config("ZIPRECRUITER_API_KEY")

YC_JOBS_BASE_URL = "https://www.workatastartup.com/api/jobs"
OTTA_BASE_URL = "https://www.otta.com/api/v0/jobs"
CLEARANCEJOBS_BASE_URL = "https://www.clearancejobs.com/api/jobs"
HEALTH_ECAREERS_BASE_URL = "https://www.healthecareers.com/api/jobs"

# ─── Deduplication Settings ───────────────────────────────────
FUZZY_MATCH_THRESHOLD = 85  # Similarity threshold for fuzzy matching (0-100)
ENABLE_FUZZY_DEDUP = True  # Enable fuzzy deduplication across sources

# ─── Matching Settings ────────────────────────────────────────
MATCHING_WEIGHTS = {
    "skills": 0.35,      # Skills overlap
    "title": 0.25,       # Title similarity
    "salary": 0.15,      # Salary match
    "category": 0.10,    # Category match
    "location": 0.10,    # Location preference
    "clearance": 0.05,   # Security clearance match
}
