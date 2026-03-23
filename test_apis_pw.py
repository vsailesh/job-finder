import asyncio
from playwright.async_api import async_playwright
import json

async def intercept_workday():
    print("--- Intercepting Workday ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        page.on("request", lambda request: print(f"[WD] {request.method} {request.resource_type} {request.url}") if request.resource_type in ["fetch", "xhr"] else None)

        try:
            await page.goto("https://mastercard.wd1.myworkdayjobs.com/CorporateCareers", wait_until="networkidle")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(e)
        await browser.close()

async def intercept_apple():
    print("\n--- Intercepting Apple ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        page.on("request", lambda request: print(f"[AP] {request.method} {request.resource_type} {request.url}") if request.resource_type in ["fetch", "xhr"] else None)

        try:
            await page.goto("https://jobs.apple.com/en-us/search?location=united-states-USA", wait_until="networkidle")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(e)
        await browser.close()
        
        
async def intercept_google():
    print("\n--- Intercepting Google ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        page.on("request", lambda request: print(f"[GO] {request.method} {request.resource_type} {request.url}") if request.resource_type in ["fetch", "xhr"] else None)

        try:
            await page.goto("https://www.google.com/about/careers/applications/jobs/results/?distance=50&q=software", wait_until="networkidle")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(e)
        await browser.close()

async def main():
    await intercept_workday()
    await intercept_apple()
    await intercept_google()

if __name__ == "__main__":
    asyncio.run(main())
