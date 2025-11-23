import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import logging
import os

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Singleton class to manage Playwright browser instance.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance.playwright = None
            cls._instance.browser = None
            cls._instance.context = None
            cls._instance.page = None
        return cls._instance

    async def initialize(self, headless: bool = False):
        """Initialize the browser if not already started."""
        if not self.playwright:
            logger.info("Starting Playwright...")
            self.playwright = await async_playwright().start()
            
            logger.info(f"Launching Browser (Headless: {headless})...")
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=[
                    '--window-position=0,0',
                    '--window-size=1280,720'
                ]
            )
            logger.info("Browser initialized successfully.")

    async def create_video_page(self) -> tuple[Page, BrowserContext]:
        """
        Create a new page with video recording enabled.
        Returns (page, context). Context must be closed to save video.
        """
        if not self.browser:
            await self.initialize()
            
        videos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
        os.makedirs(videos_dir, exist_ok=True)
        
        context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            record_video_dir=videos_dir,
            record_video_size={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        return page, context

    async def get_page(self) -> Page:
        """Get a simple page (no video) for searching."""
        if not self.browser:
            await self.initialize()
            
        if not self.context:
             self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
        if not self.page:
            self.page = await self.context.new_page()
            
        return self.page

    async def close(self):
        """Close all browser resources."""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
            
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        logger.info("Browser closed.")

# Global instance
browser_manager = BrowserManager()
