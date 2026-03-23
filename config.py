"""
Central configuration for Job Finding Agent.
Loads API keys from .env and defines search categories/keywords.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

# ─── API Keys ───────────────────────────────────────────────
USAJOBS_API_KEY = os.getenv("USAJOBS_API_KEY", "")
USAJOBS_EMAIL = os.getenv("USAJOBS_EMAIL", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# ─── Database ───────────────────────────────────────────────
DB_PATH = PROJECT_ROOT / "data" / "jobs.db"
TRACKED_COMPANIES_PATH = PROJECT_ROOT / "data" / "tracked_companies.json"

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
