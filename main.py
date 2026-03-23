#!/usr/bin/env python3
"""
Job Finding Agent — Main orchestrator.
Runs all job search agents in parallel and stores results.

Usage:
    python main.py                    # Run once, search all sources
    python main.py --schedule         # Run on a 24-hour schedule
    python main.py --dashboard        # Launch Streamlit dashboard
    python main.py --sources usajobs jsearch  # Search specific sources only
"""
import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime
from typing import List

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.live import Live
from rich import box

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from models.database import JobDatabase
from models.job import Job
from agents.usajobs_agent import USAJobsAgent
from agents.jsearch_agent import JSearchAgent
from agents.remotive_agent import RemotiveAgent
from agents.adzuna_agent import AdzunaAgent
from agents.arbeitnow_agent import ArbeitnowAgent
from agents.joinrise_agent import JoinRiseAgent
from agents.indeed_agent import IndeedScraperAgent
from agents.linkedin_agent import LinkedInAgent
from agents.glassdoor_agent import GlassdoorAgent
from agents.monster_agent import MonsterAgent
from agents.remoteok_agent import RemoteOKAgent
from agents.careers_agent import CareersAgent
from agents.dice_agent import DiceAgent

console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(config.PROJECT_ROOT / "data" / "job_finder.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("job_finder")

# Map agent names to classes
AGENT_MAP = {
    "usajobs": USAJobsAgent,
    "jsearch": JSearchAgent,
    "remotive": RemotiveAgent,
    "adzuna": AdzunaAgent,
    "arbeitnow": ArbeitnowAgent,
    "joinrise": JoinRiseAgent,
    "indeed": IndeedScraperAgent,
    "linkedin": LinkedInAgent,
    "glassdoor": GlassdoorAgent,
    "monster": MonsterAgent,
    "remoteok": RemoteOKAgent,
    "careers": CareersAgent,
    "dice": DiceAgent,
}


def print_banner():
    """Print a nice startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════╗
║          🔍  JOB FINDING AGENT  🔍                      ║  
║    Federal · State · Corporate · Remote                  ║
║    Science · Tech · Defense · Finance · Aerospace        ║
╚══════════════════════════════════════════════════════════╝
    """
    console.print(Panel(banner.strip(), style="bold cyan", box=box.DOUBLE))


def print_config_status():
    """Print which agents are configured."""
    table = Table(title="Agent Configuration", box=box.ROUNDED)
    table.add_column("Source", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Coverage")
    
    agents_info = [
        ("USAJobs", bool(config.USAJOBS_API_KEY and config.USAJOBS_EMAIL),
         "Federal government jobs"),
        ("JSearch", bool(config.RAPIDAPI_KEY),
         "LinkedIn, Indeed, Glassdoor, ZipRecruiter"),
        ("Remotive", True,
         "Remote tech jobs (no key needed)"),
        ("Adzuna", bool(config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY),
         "Global job aggregator"),
        ("Arbeitnow", True,
         "Global tech & remote jobs (no key needed)"),
        ("JoinRise", True,
         "Multi-industry jobs (no key needed)"),
        ("Indeed", True,
         "Indeed job scraper (no key needed)"),
        ("LinkedIn", True,
         "LinkedIn public jobs (no key needed)"),
        ("Glassdoor", True,
         "Glassdoor job scraper (no key needed)"),
        ("Monster", True,
         "Monster job scraper (no key needed)"),
        ("RemoteOK", True,
         "RemoteOK remote jobs (no key needed)"),
        ("Careers", True,
         "Company career pages — Greenhouse, Lever, Ashby (no key needed)"),
        ("Dice", True,
         "Dice tech jobs scraper (no key needed)"),
    ]
    
    for name, configured, coverage in agents_info:
        status = "[green]✓ Ready[/green]" if configured else "[yellow]⚠ No API key[/yellow]"
        table.add_row(name, status, coverage)
    
    console.print(table)
    console.print()


async def run_agent(agent_cls, db: JobDatabase) -> dict:
    """Run a single agent and store results."""
    agent = agent_cls()
    result = {
        "name": agent.name,
        "jobs_found": 0,
        "inserted": 0,
        "skipped": 0,
        "error": None,
    }
    
    if not agent.is_configured():
        result["error"] = "Not configured (missing API key)"
        logger.warning(f"[{agent.name}] Skipping — not configured")
        return result
    
    try:
        async with agent:
            console.print(f"  [cyan]🔄[/cyan] Searching [bold]{agent.name}[/bold]...")
            jobs = await agent.search_all_categories()
            result["jobs_found"] = len(jobs)
            
            if jobs:
                db_result = await db.insert_jobs(jobs)
                result["inserted"] = db_result["inserted"]
                result["skipped"] = db_result["skipped"]
            
            console.print(
                f"  [green]✓[/green] [bold]{agent.name}[/bold]: "
                f"{len(jobs)} found, {result['inserted']} new, "
                f"{result['skipped']} duplicates"
            )
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"[{agent.name}] Agent failed: {e}", exc_info=True)
        console.print(f"  [red]✗[/red] [bold]{agent.name}[/bold]: {e}")
    
    return result


async def run_once(sources: List[str] = None):
    """Run all configured agents once."""
    print_banner()
    print_config_status()
    
    db = JobDatabase(config.DB_PATH)
    await db.initialize()
    
    run_id = await db.start_run()
    
    console.print(Panel("🚀 Starting Job Search", style="bold green"))
    console.print(f"  Searching jobs posted in the [bold]last 24 hours[/bold]")
    console.print(f"  Categories: [cyan]{len(config.SEARCH_CATEGORIES)}[/cyan]")
    console.print(
        f"  Keywords: [cyan]{sum(len(v) for v in config.SEARCH_CATEGORIES.values())}[/cyan]"
    )
    console.print()
    
    # Determine which agents to run
    if sources:
        agent_classes = [AGENT_MAP[s] for s in sources if s in AGENT_MAP]
    else:
        agent_classes = list(AGENT_MAP.values())
    
    # Run all agents concurrently
    start_time = datetime.now()
    tasks = [run_agent(cls, db) for cls in agent_classes]
    results = await asyncio.gather(*tasks)
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Summary
    console.print()
    total_found = sum(r["jobs_found"] for r in results)
    total_new = sum(r["inserted"] for r in results)
    total_dupes = sum(r["skipped"] for r in results)
    total_errors = sum(1 for r in results if r["error"] and "Not configured" not in r["error"])
    
    # Results table
    table = Table(title="Search Results Summary", box=box.ROUNDED)
    table.add_column("Source", style="cyan")
    table.add_column("Found", justify="right")
    table.add_column("New", justify="right", style="green")
    table.add_column("Duplicates", justify="right", style="yellow")
    table.add_column("Status")
    
    for r in results:
        if r["error"]:
            status = f"[red]{r['error'][:40]}[/red]"
        else:
            status = "[green]✓ Success[/green]"
        table.add_row(
            r["name"],
            str(r["jobs_found"]),
            str(r["inserted"]),
            str(r["skipped"]),
            status,
        )
    
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_found}[/bold]",
        f"[bold green]{total_new}[/bold green]",
        f"[bold yellow]{total_dupes}[/bold yellow]",
        "",
        end_section=True,
    )
    
    console.print(table)
    console.print(f"\n  ⏱️  Completed in [bold]{elapsed:.1f}s[/bold]")
    
    # Show category breakdown
    stats = await db.get_stats(hours=24)
    if stats["by_category"]:
        cat_table = Table(title="Jobs by Category (Last 24h)", box=box.ROUNDED)
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Count", justify="right", style="green")
        for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            cat_table.add_row(cat, str(count))
        console.print()
        console.print(cat_table)
    
    if stats["by_type"]:
        type_table = Table(title="Jobs by Type (Last 24h)", box=box.ROUNDED)
        type_table.add_column("Type", style="cyan")
        type_table.add_column("Count", justify="right", style="green")
        for jtype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            type_table.add_row(jtype, str(count))
        console.print()
        console.print(type_table)
    
    # Complete the run record
    sources_searched = ",".join(r["name"] for r in results if not r["error"])
    await db.complete_run(run_id, total_found, total_new, total_dupes, total_errors, sources_searched)
    
    console.print(
        f"\n  💾 Database: [bold]{config.DB_PATH}[/bold]"
    )
    console.print(
        f"  🌐 Dashboard: Run [bold cyan]python main.py --dashboard[/bold cyan] to view results"
    )
    console.print()


def run_scheduled():
    """Run on a 24-hour schedule using APScheduler."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    
    console.print(Panel("⏰ Scheduled Mode — Running every 24 hours", style="bold blue"))
    console.print("  Press Ctrl+C to stop\n")
    
    scheduler = BlockingScheduler()
    
    def scheduled_job():
        console.print(f"\n{'='*60}")
        console.print(f"  Scheduled run at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        console.print(f"{'='*60}\n")
        asyncio.run(run_once())
    
    # Run immediately on start
    scheduled_job()
    
    # Then schedule every 24 hours
    scheduler.add_job(scheduled_job, "interval", hours=24, id="job_search")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("\n[yellow]Scheduler stopped.[/yellow]")


def launch_dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    dashboard_path = config.PROJECT_ROOT / "dashboard" / "app.py"
    console.print(f"🌐 Launching dashboard: {dashboard_path}")
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", str(dashboard_path),
        "--server.port", "8501",
        "--server.headless", "true",
    ])


def main():
    parser = argparse.ArgumentParser(
        description="🔍 Job Finding Agent — Search jobs across federal, state, and corporate sources"
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run on a 24-hour schedule"
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Launch Streamlit dashboard"
    )
    parser.add_argument(
        "--sources", nargs="+",
        choices=list(AGENT_MAP.keys()),
        help="Specify which sources to search (default: all)"
    )
    
    args = parser.parse_args()
    
    if args.dashboard:
        launch_dashboard()
    elif args.schedule:
        run_scheduled()
    else:
        asyncio.run(run_once(sources=args.sources))


if __name__ == "__main__":
    main()
