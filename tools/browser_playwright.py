import os
import asyncio
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class PlaywrightBrowserTool:
    """
    Playwright Browser Automation Tool for rich web interaction, form filling, text extraction, and screenshot capture.
    """

    def __init__(self, headless: bool = None):
        self.headless = headless if headless is not None else getattr(config, "PLAYWRIGHT_HEADLESS", True)
        self._browser = None
        self._page = None
        self._playwright = None

    async def _ensure_page(self):
        if self._page is None or self._page.is_closed():
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()

    async def navigate_to_url(self, url: str) -> str:
        """Navigates to specified URL."""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        try:
            await self._ensure_page()
            response = await self._page.goto(url, timeout=15000)
            title = await self._page.title()
            return f"Successfully navigated to {url}. Page Title: '{title}'"
        except Exception as e:
            return f"Failed to navigate to {url}: {e}"

    async def extract_page_text(self) -> str:
        """Extracts visible text content from the current active web page."""
        try:
            await self._ensure_page()
            text = await self._page.evaluate("() => document.body.innerText")
            clean_text = "\n".join([line.strip() for line in text.splitlines() if line.strip()])
            return clean_text[:3000] if len(clean_text) > 3000 else clean_text
        except Exception as e:
            return f"Failed to extract page text: {e}"

    async def click_element(self, selector: str) -> str:
        """Clicks an HTML element matching CSS/XPath selector."""
        try:
            await self._ensure_page()
            await self._page.click(selector, timeout=5000)
            return f"Successfully clicked element '{selector}'."
        except Exception as e:
            return f"Failed to click element '{selector}': {e}"

    async def fill_form(self, selector: str, text: str) -> str:
        """Fills input text into a form element matching CSS selector."""
        try:
            await self._ensure_page()
            await self._page.fill(selector, text, timeout=5000)
            return f"Successfully filled text into element '{selector}'."
        except Exception as e:
            return f"Failed to fill form element '{selector}': {e}"

    async def take_screenshot(self, path: str = None) -> str:
        """Takes a screenshot of current page."""
        if not path:
            temp_dir = os.path.join(os.path.dirname(__file__), "..", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            path = os.path.abspath(os.path.join(temp_dir, "web_screenshot.png"))
        try:
            await self._ensure_page()
            await self._page.screenshot(path=path, full_page=False)
            return f"Successfully captured web screenshot to: {path}"
        except Exception as e:
            return f"Failed to capture screenshot: {e}"

    async def close(self):
        """Closes browser instance."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()


# Helper sync functions for tool calls
def playwright_navigate(url: str) -> str:
    tool = PlaywrightBrowserTool()
    return asyncio.run(tool.navigate_to_url(url))


def playwright_extract_text() -> str:
    tool = PlaywrightBrowserTool()
    return asyncio.run(tool.extract_page_text())


def playwright_click(selector: str) -> str:
    tool = PlaywrightBrowserTool()
    return asyncio.run(tool.click_element(selector))


def playwright_fill(selector: str, text: str) -> str:
    tool = PlaywrightBrowserTool()
    return asyncio.run(tool.fill_form(selector, text))


def playwright_screenshot(path: str = None) -> str:
    tool = PlaywrightBrowserTool()
    return asyncio.run(tool.take_screenshot(path))


if __name__ == "__main__":
    print("[PlaywrightBrowserTool] Loaded successfully.")
