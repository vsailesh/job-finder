# 🔍 Job Finding Agent

A multi-source, automated job-finding agent that searches **federal, state, and corporate** job postings from the **last 24 hours** across high-value sectors. Features **profile-based job matching** and **automated applications**.

## Features

- **19 job sources** — Federal, corporate aggregators, tech startups, healthcare, defense, and more
- **11 search categories** — Science, Tech, Defense, Finance, Healthcare, and more
- **Turso Cloud or SQLite** — Cloud sync with automatic fallback to local database
- **Profile system** — Create applicant profiles with skills, preferences, and resumes
- **Smart matching** — Weighted scoring across skills, title similarity, salary, location, and clearance
- **Fuzzy deduplication** — Automatic duplicate detection across sources using RapidFuzz
- **Config-driven architecture** — Enable/disable sources dynamically via config
- **Automated applications** — Apply to jobs directly from the dashboard
- **Scheduled runs** — 24-hour automatic job searching with APScheduler
- **Interactive dashboard** — Streamlit web UI with filters, charts, and CSV export
- **100+ tracked companies** — Fortune 500, FAANG+, healthcare systems, defense contractors

## Sectors Covered

| Category | Example Keywords |
|----------|-----------------|
| **Science & Technology** | Software Engineer, Data Scientist, AI/ML, Cybersecurity |
| **Manufacturing** | CNC, Production, Quality Control, Industrial |
| **Pharmacy & Biotech** | Pharmacist, Clinical Research, Bioinformatics |
| **Defense & Military** | DoD, Intelligence Analyst, Security Clearance |
| **Finance** | Fintech, Quantitative Analyst, Risk Analyst |
| **Robotics & Automation** | Robotics Engineer, Mechatronics, PLC |
| **Nuclear** | Reactor Engineer, Radiation Protection |
| **Aerospace & Drones** | Aerospace Engineer, UAV, Avionics, Satellite |
| **Healthcare** | Registered Nurse, Physician, Surgeon, Medical Technologist |
| **State Government (DMV)** | Maryland, Virginia, DC Government jobs |

## Data Sources

| Source | Coverage | Auth Required |
|--------|----------|---------------|
| **USAJobs** | Federal government | Free API key |
| **JSearch** | LinkedIn, Indeed, Glassdoor, ZipRecruiter | Free RapidAPI key |
| **Remotive** | Remote tech jobs | None |
| **Adzuna** | Global job aggregator | Free API key |
| **Arbeitnow** | Global tech & remote jobs | None |
| **JoinRise** | Multi-industry jobs | None |
| **Indeed** | Indeed job scraper | None |
| **LinkedIn** | LinkedIn public jobs | None |
| **Glassdoor** | Glassdoor job scraper | None |
| **Monster** | Monster job scraper | None |
| **RemoteOK** | RemoteOK remote jobs | None |
| **Careers** | Company career pages (100+ companies) | None |
| **Dice** | Dice tech jobs | None |
| **ZipRecruiter** (NEW) | ZipRecruiter job board | Free API key |
| **YC Jobs** (NEW) | YC-backed startups | None |
| **Otta** (NEW) | Tech startup jobs | None |
| **ClearanceJobs** (NEW) | Defense/clearance jobs | None |
| **Health eCareers** (NEW) | Healthcare jobs | None |
| **State Government** (NEW) | MD/VA/DC government jobs | None |

## Quick Start

### 1. Install Dependencies

```bash
cd job-finder-agent
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Get your free API keys:**
- **USAJobs**: [developer.usajobs.gov](https://developer.usajobs.gov/APIRequest/Index)
- **JSearch**: [RapidAPI JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch)
- **Adzuna**: [developer.adzuna.com](https://developer.adzuna.com/)
- **ScraperAPI** (optional, for Indeed): [scraperapi.com](https://www.scraperapi.com/)
- **Remotive, Arbeitnow, JoinRise, LinkedIn, Glassdoor, Monster, RemoteOK, Careers, Dice**: No key needed ✓
- **Turso** (optional, for cloud database): [turso.tech](https://turso.tech/)

> **Note**: The agent works with any subset of keys — unconfigured sources are gracefully skipped.

### 3. Run the Agent

```bash
# Search all configured sources once
python main.py

# Search specific sources only
python main.py --sources usajobs remotive

# Run on a 24-hour schedule
python main.py --schedule

# Launch the web dashboard
python main.py --dashboard
```

## Profiles & Automated Applications

Create applicant profiles to enable job matching and automated applications:

```python
# Example profile structure
{
    "name": "Senior Engineer",
    "full_name": "John Doe",
    "email": "john@example.com",
    "phone": "555-1234",
    "resume_path": "data/resumes/john_doe.pdf",
    "skills": ["Python", "React", "AWS", "Docker"],
    "preferred_categories": ["Science & Technology"],
    "preferred_job_types": ["Full-time", "Remote"],
    "target_salary_min": 120000,
    "years_experience": 5,
    "security_clearance": "secret",
    "education": "B.S. Computer Science",
    "willing_to_relocate": true
}
```

Profiles are stored as JSON in the `profiles/` directory. The dashboard allows you to:
- Create and manage profiles
- Match jobs against your profile (scored 0.0-1.0)
- Auto-generate cover letters from templates
- Apply to jobs with one click

## v2.0 New Features

### Fuzzy Deduplication
Jobs from different sources are now automatically deduplicated using fuzzy string matching:
- Title, company, and location similarity detection
- URL normalization for same job postings
- Configurable similarity threshold (default: 85%)
- Automatic updates with newer job data

### Smart Matching
Profile-to-job matching now uses weighted scoring:
- **Skills overlap (35%)** — Fuzzy matching of skills against job description
- **Title similarity (25%)** — Seniority level and keyword matching
- **Salary match (15%)** — Compares against your target salary range
- **Category match (10%)** — Matches your preferred categories
- **Location preference (10%)** — Remote vs location-based preferences
- **Clearance match (5%)** — Security clearance level matching

### Config-Driven Architecture
Enable/disable sources via `config.py`:
```python
ENABLED_SOURCES = {
    "usajobs": True,
    "jsearch": True,
    "ziprecruiter": True,
    "yc_jobs": True,
    # ... toggle any source on/off
}
```

### Expanded Company Coverage
The `tracked_companies.json` now includes **100+ companies**:
- **Fortune 500** — JPMorgan Chase, Goldman Sachs, Bank of America, etc.
- **FAANG+** — Google, Meta, Apple, Microsoft, Netflix, Amazon
- **Tech Leaders** — Stripe, Airbnb, Cloudflare, Datadog, GitLab, Coinbase
- **Defense Contractors** — Lockheed Martin, Booz Allen, Northrop Grumman, Raytheon
- **Healthcare Systems** — Johns Hopkins, Mayo Clinic, Cleveland Clinic, Kaiser
- **AI/ML Companies** — OpenAI, Anthropic, DeepMind, Cohere, Hugging Face
- **Fintech** — PayPal, Intuit, Fidelity, Robinhood, Plaid, Chime

## Dashboard

The Streamlit dashboard provides:
- **Summary metrics** — total jobs, federal/corporate/remote breakdown
- **Interactive charts** — jobs by category, source, type, top employers
- **Filterable job table** — search, sort, filter by source/category/type/salary
- **Analytics** — salary distribution, location treemap, employment types
- **CSV export** — download filtered results

```bash
python main.py --dashboard
# Opens at http://localhost:8501
```

## Project Structure

```
job-finder-agent/
├── main.py                  # CLI orchestrator (run-once, schedule, dashboard)
├── config.py                # API keys, endpoints, search categories, enabled sources
├── requirements.txt
├── .env.example
├── agents/
│   ├── base_agent.py        # Async base with retry/rate-limit
│   ├── usajobs_agent.py     # Federal government jobs
│   ├── jsearch_agent.py     # Corporate aggregator (RapidAPI)
│   ├── remotive_agent.py    # Remote tech jobs
│   ├── adzuna_agent.py      # Global job aggregator
│   ├── arbeitnow_agent.py   # Global tech & remote jobs
│   ├── joinrise_agent.py    # Multi-industry jobs
│   ├── indeed_agent.py      # Indeed job scraper
│   ├── linkedin_agent.py    # LinkedIn public jobs
│   ├── glassdoor_agent.py   # Glassdoor job scraper
│   ├── monster_agent.py     # Monster job scraper
│   ├── remoteok_agent.py    # RemoteOK remote jobs
│   ├── careers_agent.py     # Company career pages (100+ companies)
│   ├── dice_agent.py        # Dice tech jobs
│   ├── apply_agent.py       # Automated job applications
│   ├── ziprecruiter_agent.py    # ZipRecruiter API (NEW)
│   ├── yc_jobs_agent.py         # YC-backed startup jobs (NEW)
│   ├── otta_agent.py            # Tech startup jobs (NEW)
│   ├── clearancejobs_agent.py   # Defense/clearance jobs (NEW)
│   ├── health_ecareers_agent.py # Healthcare jobs (NEW)
│   └── state_government_agent.py # MD/VA/DC government jobs (NEW)
├── models/
│   ├── job.py               # Job dataclass
│   ├── database.py          # Async SQLite with fuzzy dedup
│   ├── turso_database.py    # Turso cloud database
│   └── profile.py           # Applicant profile model with smart matching
├── dashboard/
│   └── app.py               # Streamlit dashboard
├── data/
│   ├── jobs.db              # SQLite database (auto-created)
│   ├── job_finder.log       # Log file
│   ├── resumes/             # Resume PDFs for applications
│   └── tracked_companies.json  # 100+ Fortune 500, FAANG+, healthcare, defense
└── profiles/                # Applicant profiles (JSON)
```
