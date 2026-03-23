"""
Auto-Apply Agent — uses Playwright to automatically apply to queued jobs.
Supports Indeed Easy Apply, LinkedIn Quick Apply, and generic career pages.
Falls back to 'manual' status for complex ATS forms.
"""
import asyncio
import logging
import re
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List
from pathlib import Path

from models.profile import Profile
from models.database import JobDatabase
import config

logger = logging.getLogger(__name__)


class ApplyAgent:
    """Automated job application agent using Playwright."""

    # Application attempt delay (seconds) — polite rate limiting
    MIN_DELAY = 5
    MAX_DELAY = 15

    def __init__(self, profile: Profile, db: JobDatabase):
        self.profile = profile
        self.db = db
        self.stats = {"applied": 0, "failed": 0, "manual": 0, "skipped": 0}

    async def apply_to_queued(self, limit: int = 10) -> Dict[str, int]:
        """Process queued applications for this profile."""
        apps = self.db.get_applications_sync(
            profile_name=self.profile.name, status="queued"
        )

        if not apps:
            logger.info(f"[apply] No queued applications for profile '{self.profile.name}'")
            return self.stats

        logger.info(f"[apply] Processing {min(len(apps), limit)} of {len(apps)} queued applications")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("[apply] playwright not installed — run: pip install playwright && python -m playwright install chromium")
            return self.stats

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )

            for app in apps[:limit]:
                app_id = app["id"]
                url = app.get("url", "")
                title = app.get("title", "Unknown")
                company = app.get("company", "Unknown")

                if not url or url == "—":
                    self.db.update_application_status(
                        app_id, "failed", error="No application URL"
                    )
                    self.stats["failed"] += 1
                    continue

                logger.info(f"[apply] Applying to: {title} @ {company}")

                try:
                    page = await context.new_page()
                    result = await self._apply_to_job(page, app)
                    await page.close()

                    if result == "applied":
                        self.stats["applied"] += 1
                        logger.info(f"[apply] ✓ Applied: {title} @ {company}")
                    elif result == "manual":
                        self.stats["manual"] += 1
                        logger.info(f"[apply] ⚠ Manual required: {title} @ {company}")
                    else:
                        self.stats["failed"] += 1
                        logger.warning(f"[apply] ✗ Failed: {title} @ {company}")

                except Exception as e:
                    self.db.update_application_status(
                        app_id, "failed", error=str(e)[:500]
                    )
                    self.stats["failed"] += 1
                    logger.error(f"[apply] Error applying to {title}: {e}")

                # Polite delay
                import random
                delay = random.randint(self.MIN_DELAY, self.MAX_DELAY)
                logger.debug(f"[apply] Waiting {delay}s before next application")
                await asyncio.sleep(delay)

            await browser.close()

        logger.info(
            f"[apply] Session complete — Applied: {self.stats['applied']}, "
            f"Manual: {self.stats['manual']}, Failed: {self.stats['failed']}"
        )
        return self.stats

    async def _dismiss_popups(self, page) -> None:
        """Dismiss cookie consent banners, modals, and overlay popups."""
        dismiss_selectors = [
            # Cookie consent buttons
            'button:has-text("Accept")', 'button:has-text("Accept All")',
            'button:has-text("Accept Cookies")', 'button:has-text("I Accept")',
            'button:has-text("OK")', 'button:has-text("Got it")',
            'button:has-text("Agree")', 'button:has-text("Close")',
            'button:has-text("Dismiss")', 'button:has-text("No Thanks")',
            # Common close buttons
            '[class*="cookie"] button', '[id*="cookie"] button',
            '[class*="consent"] button', '[class*="popup"] button[class*="close"]',
            '[class*="modal"] button[class*="close"]',
            '.mfp-close', 'button.mfp-close',  # Magnific Popup (Adzuna uses this)
            '[class*="overlay"] button[class*="close"]',
            'button[aria-label="Close"]', 'button[aria-label="close"]',
        ]
        for sel in dismiss_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        # Also try pressing Escape to close modals
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _follow_adzuna_redirect(self, page, url: str) -> str:
        """Follow Adzuna detail page to the actual employer apply URL."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)
            await asyncio.sleep(1)

            # Look for the "Apply" or external link button on Adzuna
            apply_selectors = [
                'a.a-apply-btn', 'a[class*="apply"]',
                'a:has-text("Apply")', 'a:has-text("Apply for this job")',
                'button:has-text("Apply")',
            ]
            for sel in apply_selectors:
                btn = await page.query_selector(sel)
                if btn:
                    href = await btn.get_attribute("href")
                    if href and href.startswith("http"):
                        return href
                    # Click and wait for navigation
                    try:
                        async with page.expect_navigation(timeout=10000):
                            await btn.click()
                        return page.url
                    except Exception:
                        await btn.click()
                        await asyncio.sleep(3)
                        return page.url

            return page.url
        except Exception as e:
            logger.debug(f"[apply] Adzuna redirect error: {e}")
            return url

    async def _apply_to_job(self, page, app: dict) -> str:
        """
        Navigate to job URL and attempt to apply.
        Returns: 'applied', 'manual', or 'failed'
        """
        app_id = app["id"]
        url = app.get("url", "")
        title = app.get("title", "Unknown")
        company = app.get("company", "Unknown")
        source = app.get("source", "")

        cover_letter = app.get("cover_letter", "")
        if not cover_letter:
            cover_letter = self.profile.render_cover_letter(title, company)

        # If URL is from an aggregator, follow to the actual employer page
        if "adzuna.com" in url:
            url = await self._follow_adzuna_redirect(page, url)
            logger.info(f"[apply] Adzuna redirected to: {url[:80]}")

        try:
            if page.url != url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            await self._dismiss_popups(page)
        except Exception as e:
            self.db.update_application_status(app_id, "failed", error=f"Navigation failed: {e}")
            return "failed"

        page_url = page.url.lower()

        # Detect application type
        if "indeed.com" in page_url:
            return await self._apply_indeed(page, app_id, cover_letter)
        elif "linkedin.com" in page_url:
            return await self._apply_linkedin(page, app_id, cover_letter)
        elif any(ats in page_url for ats in ["greenhouse.io", "lever.co", "workday.com", "icims.com"]):
            # Complex ATS — mark for manual apply
            self.db.update_application_status(
                app_id, "manual",
                notes=f"Complex ATS detected ({page_url.split('/')[2]}). Apply manually at: {url}"
            )
            return "manual"
        else:
            return await self._apply_generic(page, app_id, cover_letter)

    async def _apply_indeed(self, page, app_id: int, cover_letter: str) -> str:
        """Handle Indeed application."""
        try:
            # Look for "Apply now" or "Easy Apply" button
            apply_btn = await page.query_selector('[id*="apply"], [class*="apply"], button:has-text("Apply")')
            if apply_btn:
                await apply_btn.click()
                await asyncio.sleep(3)

                # Check if redirected to external site
                if "indeed.com" not in page.url.lower():
                    self.db.update_application_status(
                        app_id, "manual",
                        notes=f"Redirected to external site: {page.url}"
                    )
                    return "manual"

                # Try to fill form fields
                filled = await self._fill_common_fields(page, cover_letter)
                if filled == "applied":
                    self.db.update_application_status(
                        app_id, "applied", notes="Applied via Indeed"
                    )
                    return "applied"
                elif filled == "manual":
                    self.db.update_application_status(
                        app_id, "manual", notes="Validation errors or uncertain success on Indeed."
                    )
                    return "manual"

            # No easy apply — mark as manual
            self.db.update_application_status(
                app_id, "manual",
                notes=f"No Easy Apply found. Apply manually at: {page.url}"
            )
            return "manual"

        except Exception as e:
            self.db.update_application_status(app_id, "failed", error=str(e)[:500])
            return "failed"

    async def _apply_linkedin(self, page, app_id: int, cover_letter: str) -> str:
        """Handle LinkedIn application."""
        try:
            # LinkedIn usually requires login for Easy Apply
            apply_btn = await page.query_selector('button:has-text("Easy Apply"), button:has-text("Apply")')
            if apply_btn:
                # Check if login required
                login_form = await page.query_selector('[class*="login"], [data-test*="login"]')
                if login_form:
                    self.db.update_application_status(
                        app_id, "manual",
                        notes="LinkedIn login required. Apply manually."
                    )
                    return "manual"

            self.db.update_application_status(
                app_id, "manual",
                notes=f"LinkedIn Easy Apply requires login. Apply at: {page.url}"
            )
            return "manual"

        except Exception as e:
            self.db.update_application_status(app_id, "failed", error=str(e)[:500])
            return "failed"

    async def _apply_generic(self, page, app_id: int, cover_letter: str) -> str:
        """Handle generic career page applications."""
        try:
            # Look for common apply buttons
            apply_selectors = [
                'a:has-text("Apply")', 'button:has-text("Apply")',
                'a:has-text("Submit Application")', 'button:has-text("Submit")',
                '[class*="apply"]', '[id*="apply"]',
            ]

            clicked = False
            for selector in apply_selectors:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await asyncio.sleep(3)
                    clicked = True
                    break

            if clicked:
                filled = await self._fill_common_fields(page, cover_letter)
                if filled == "applied":
                    self.db.update_application_status(
                        app_id, "applied", notes="Applied via career page"
                    )
                    return "applied"
                elif filled == "manual":
                    self.db.update_application_status(
                        app_id, "manual", notes="Validation errors or uncertain success."
                    )
                    return "manual"

            # Mark for manual if can't auto-apply
            self.db.update_application_status(
                app_id, "manual",
                notes=f"Could not auto-apply. Apply manually at: {page.url}"
            )
            return "manual"

        except Exception as e:
            self.db.update_application_status(app_id, "failed", error=str(e)[:500])
            return "failed"

    async def _fill_common_fields(self, page, cover_letter: str) -> str:
        """Try to fill common application form fields and verify submission."""
        try:
            filled_any = False

            # Name fields
            name_selectors = [
                'input[name*="name" i]', 'input[placeholder*="name" i]',
                'input[id*="name" i]', 'input[aria-label*="name" i]',
            ]
            for sel in name_selectors:
                field = await page.query_selector(sel)
                if field:
                    await field.fill(self.profile.full_name)
                    filled_any = True
                    break

            # Email
            email_selectors = [
                'input[type="email"]', 'input[name*="email" i]',
                'input[placeholder*="email" i]', 'input[id*="email" i]',
            ]
            for sel in email_selectors:
                field = await page.query_selector(sel)
                if field:
                    await field.fill(self.profile.email)
                    filled_any = True
                    break

            # Phone
            phone_selectors = [
                'input[type="tel"]', 'input[name*="phone" i]',
                'input[placeholder*="phone" i]', 'input[id*="phone" i]',
            ]
            for sel in phone_selectors:
                field = await page.query_selector(sel)
                if field:
                    await field.fill(self.profile.phone)
                    filled_any = True
                    break

            # Resume upload
            if self.profile.resume_path and os.path.exists(self.profile.resume_path):
                file_inputs = await page.query_selector_all('input[type="file"]')
                for fi in file_inputs:
                    accept = await fi.get_attribute("accept") or ""
                    name_attr = await fi.get_attribute("name") or ""
                    if any(x in accept.lower() for x in ["pdf", "doc", "resume"]) or \
                       any(x in name_attr.lower() for x in ["resume", "cv", "file"]):
                        await fi.set_input_files(self.profile.resume_path)
                        filled_any = True
                        break
                else:
                    # If only one file input, use it
                    if len(file_inputs) == 1:
                        await file_inputs[0].set_input_files(self.profile.resume_path)
                        filled_any = True

            # Cover letter
            if cover_letter:
                cover_selectors = [
                    'textarea[name*="cover" i]', 'textarea[name*="letter" i]',
                    'textarea[placeholder*="cover" i]', 'textarea[id*="cover" i]',
                    'textarea[name*="message" i]',
                ]
                for sel in cover_selectors:
                    field = await page.query_selector(sel)
                    if field:
                        await field.fill(cover_letter)
                        filled_any = True
                        break

            # Try to submit
            if filled_any:
                submit_selectors = [
                    'button[type="submit"]', 'input[type="submit"]',
                    'button:has-text("Submit")', 'button:has-text("Apply")',
                    'button:has-text("Send")',
                ]
                for sel in submit_selectors:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        return await self._verify_submission(page)

            return "none"

        except Exception as e:
            logger.debug(f"[apply] Field fill error: {e}")
            return "failed"

    async def _verify_submission(self, page) -> str:
        """
        Verify if the submission was successful by checking the page state post-submit.
        Returns: 'applied', 'manual', or 'failed'
        """
        try:
            # Wait a few seconds for navigation or dynamic error messages to appear
            await asyncio.sleep(4)
            
            content = await page.content()
            content_lower = content.lower()
            
            # 1. Check for success indicators
            success_keywords = [
                "application submitted", "application received", "thank you for applying",
                "success", "successfully applied", "application complete"
            ]
            
            if "success" in page.url.lower() or "thank-you" in page.url.lower():
                return "applied"
                
            for keyword in success_keywords:
                if keyword in content_lower:
                    return "applied"

            # 2. Check for validation errors
            error_keywords = [
                "is required", "invalid email", "enter a valid", "please fix", 
                "field is required", "captcha", "are you legally authorized"
            ]
            
            error_elements_found = False
            error_sels = ['[class*="error"]', '[class*="invalid"]', '[id*="error"]']
            for sel in error_sels:
                elements = await page.query_selector_all(sel)
                for el in elements:
                    if await el.is_visible():
                        text = await el.inner_text()
                        if text and len(text) > 3:
                            error_elements_found = True
                            break
                if error_elements_found:
                    break
                    
            if error_elements_found or any(keyword in content_lower for keyword in error_keywords):
                return "manual"

            # 3. Uncertain state: Neither obvious error nor obvious success. 
            # Default to manual to ensure accuracy.
            return "manual"
            
        except Exception as e:
            logger.debug(f"[apply] Verification error: {e}")
            return "manual"
