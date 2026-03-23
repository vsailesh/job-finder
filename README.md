# 🔍 Job Finding Agent

A multi-source, automated job-finding agent that searches **federal, state, and corporate** job postings from the **last 24 hours** across high-value sectors.

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

## Data Sources

| Source | Coverage | Auth Required |
|--------|----------|---------------|
| **USAJobs** | Federal government | Free API key |
| **JSearch** | LinkedIn, Indeed, Glassdoor, ZipRecruiter | Free RapidAPI key |
| **Remotive** | Remote tech jobs | None |
| **Adzuna** | Global job aggregator | Free API key |

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
- **Remotive**: No key needed ✓

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
├── config.py                # API keys, endpoints, search categories
├── requirements.txt
├── .env.example
├── agents/
│   ├── base_agent.py        # Async base with retry/rate-limit
│   ├── usajobs_agent.py     # Federal government jobs
│   ├── jsearch_agent.py     # Corporate aggregator
│   ├── remotive_agent.py    # Remote tech jobs
│   └── adzuna_agent.py      # Broad aggregator
├── models/
│   ├── job.py               # Job dataclass
│   └── database.py          # Async SQLite with dedup
├── dashboard/
│   └── app.py               # Streamlit dashboard
└── data/
    ├── jobs.db              # SQLite database (auto-created)
    └── job_finder.log       # Log file
```
