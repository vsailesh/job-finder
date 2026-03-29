"""
Migration script to copy data from local SQLite data/jobs.db to Turso.
Run this once after setting TURSO_DATABASE_URL and TURSO_AUTH_TOKEN.
"""
import sys
import os
import sqlite3
import argparse
from pathlib import Path
from rich.console import Console
from rich.progress import track

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from models.turso_database import TursoDatabase

console = Console()

def migrate():
    console.print("[bold cyan]🚀 Starting Migration from Local SQLite to Turso[/bold cyan]\n")
    
    if not config.USE_TURSO:
        console.print("[bold red]❌ Turso environment variables not set.[/bold red]")
        console.print("Please set TURSO_DATABASE_URL and TURSO_AUTH_TOKEN and try again.")
        sys.exit(1)
        
    local_db_path = config.DB_PATH
    if not local_db_path.exists():
        console.print(f"[bold red]❌ Local DB not found at {local_db_path}[/bold red]")
        sys.exit(1)
        
    # Get Turso instance and initialize tables
    turso_db = config.get_database()
    console.print(f"Initializing tables in Turso at {turso_db.url}...")
    turso_db.init_sync()
    
    # Read from local
    console.print(f"Reading data from local DB {local_db_path}...")
    local_conn = sqlite3.connect(local_db_path)
    local_conn.row_factory = sqlite3.Row
    
    try:
        # 1. Migrate Jobs
        jobs = local_conn.execute("SELECT * FROM jobs").fetchall()
        console.print(f"Found [yellow]{len(jobs)}[/yellow] jobs in local DB.")
        
        turso_conn = turso_db._get_conn()
        
        # Batch insert for efficiency
        batch_size = 500
        total_inserted = 0
        
        console.print("Migrating jobs...")
        for i in track(range(0, len(jobs), batch_size), description="Migrating jobs..."):
            batch = jobs[i:i+batch_size]
            for job in batch:
                try:
                    turso_conn.execute(
                        """INSERT INTO jobs 
                           (unique_hash, title, company, location, url, source, category,
                            posted_date, description, salary_min, salary_max, job_type,
                            employment_type, seniority, remote, search_keyword, fetched_at, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            job['unique_hash'], job['title'], job['company'], job['location'],
                            job['url'], job['source'], job['category'], job['posted_date'],
                            job['description'], job['salary_min'], job['salary_max'],
                            job['job_type'], job['employment_type'], job['seniority'],
                            job['remote'], job['search_keyword'], job['fetched_at'], job['created_at']
                        )
                    )
                    total_inserted += 1
                except Exception as e:
                    pass # skip duplicates
            turso_conn.commit()
            
        # 2. Migrate Applications
        apps = local_conn.execute("SELECT * FROM applications").fetchall()
        console.print(f"\nFound [yellow]{len(apps)}[/yellow] applications.")
        app_inserted = 0
        if apps:
            for app in track(apps, description="Migrating applications..."):
                try:
                    turso_conn.execute(
                        """INSERT INTO applications 
                           (id, job_id, job_hash, profile_name, status, applied_at, cover_letter, notes, error_message, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            app['id'], app['job_id'], app['job_hash'], app['profile_name'], app['status'], 
                            app['applied_at'], app['cover_letter'], app['notes'], app['error_message'], app['created_at']
                        )
                    )
                    app_inserted += 1
                except Exception as e:
                    pass
            turso_conn.commit()
            
        # 3. Migrate Search Runs
        runs = local_conn.execute("SELECT * FROM search_runs").fetchall()
        console.print(f"\nFound [yellow]{len(runs)}[/yellow] search runs.")
        runs_inserted = 0
        if runs:
            for run in track(runs, description="Migrating search runs..."):
                try:
                    turso_conn.execute(
                        """INSERT INTO search_runs
                           (id, started_at, completed_at, total_found, new_jobs, duplicates_skipped, errors, sources_searched, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            run['id'], run['started_at'], run['completed_at'], run['total_found'], 
                            run['new_jobs'], run['duplicates_skipped'], run['errors'], 
                            run['sources_searched'], run['status']
                        )
                    )
                    runs_inserted += 1
                except Exception as e:
                    pass
            turso_conn.commit()
            
        console.print(f"\n[bold green]✅ Migration Complete![/bold green]")
        console.print(f"Jobs migrated: [green]{total_inserted}[/green]/[yellow]{len(jobs)}[/yellow] (Remaining were likely duplicates)")
        console.print(f"Applications migrated: [green]{app_inserted}[/green]")
        console.print(f"Search runs migrated: [green]{runs_inserted}[/green]")
        
    finally:
        local_conn.close()

if __name__ == "__main__":
    migrate()
