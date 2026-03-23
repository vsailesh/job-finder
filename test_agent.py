import sys
sys.path.append('.')
import asyncio
from agents.careers_agent import CareersAgent

async def test():
    async with CareersAgent() as agent:
        print("Testing Workday scraper via internal method...")
        company = {"name": "Mastercard", "slug": "mastercard/CorporateCareers", "platform": "workday"}
        jobs = await agent._fetch_workday(company)
        print(f"Found {len(jobs)} jobs for Mastercard")
        for job in jobs[:5]:
            print(f"{job.title} | {job.category} | {job.url} | {job.remote}")

if __name__ == "__main__":
    asyncio.run(test())
