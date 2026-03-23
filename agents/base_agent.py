"""
Abstract base class for all job search agents.
Provides retry logic, rate limiting, and logging.
"""
import asyncio
import aiohttp
import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from models.job import Job
import config

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for job search agents."""
    
    name: str = "base"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(config.CONCURRENT_REQUESTS)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT)
        )
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _request(
        self,
        method: str,
        url: str,
        headers: dict = None,
        params: dict = None,
        retries: int = None,
        **kwargs,
    ) -> Optional[dict]:
        """Make an HTTP request with retry logic and rate limiting."""
        if retries is None:
            retries = config.MAX_RETRIES
        
        async with self._semaphore:
            for attempt in range(retries):
                try:
                    async with self.session.request(
                        method, url, headers=headers, params=params, **kwargs
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            wait = config.RETRY_DELAY * (2 ** attempt)
                            logger.warning(
                                f"[{self.name}] Rate limited, waiting {wait}s"
                            )
                            await asyncio.sleep(wait)
                        elif response.status in (401, 403):
                            # Auth/permission errors — don't retry
                            text = await response.text()
                            logger.error(
                                f"[{self.name}] Auth error {response.status}: {text[:200]}"
                            )
                            return None
                        elif response.status >= 500:
                            text = await response.text()
                            logger.error(
                                f"[{self.name}] Server error {response.status}: {text[:200]}"
                            )
                            await asyncio.sleep(config.RETRY_DELAY)
                        else:
                            # Other 4xx — don't retry
                            text = await response.text()
                            logger.error(
                                f"[{self.name}] HTTP {response.status}: {text[:200]}"
                            )
                            return None
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{self.name}] Timeout (attempt {attempt + 1}/{retries})"
                    )
                except aiohttp.ClientError as e:
                    logger.error(
                        f"[{self.name}] Request error: {e} (attempt {attempt + 1}/{retries})"
                    )
                    await asyncio.sleep(config.RETRY_DELAY)
        
        logger.error(f"[{self.name}] All {retries} retries exhausted for {url}")
        return None
    
    @abstractmethod
    async def search(self, keyword: str, category: str) -> List[Job]:
        """Search for jobs matching the keyword. Must be implemented by subclasses."""
        ...
    
    async def search_all_categories(self) -> List[Job]:
        """Search across all configured categories and keywords."""
        all_jobs = []
        
        for category, keywords in config.SEARCH_CATEGORIES.items():
            logger.info(f"[{self.name}] Searching category: {category}")
            
            tasks = [self.search(kw, category) for kw in keywords]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"[{self.name}] Error searching '{keywords[i]}': {result}"
                    )
                elif result:
                    all_jobs.extend(result)
        
        logger.info(f"[{self.name}] Total jobs found: {len(all_jobs)}")
        return all_jobs
    
    def is_configured(self) -> bool:
        """Check if the agent has required API keys configured."""
        return True
