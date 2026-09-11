import asyncio
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def take_screenshot(url: str, output_path: str = "screenshot.png") -> str:
    """Navigates to URL, waits for complete network/DOM render, and captures a clean screenshot."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1500)  # Render delay for dynamic JS/CSS canvas
            await page.screenshot(path=output_path, full_page=False)
            await browser.close()
            return f"Screenshot saved successfully to '{output_path}'"
        except Exception as e:
            await browser.close()
            return f"Failed to capture screenshot: {e}"


async def play_youtube_video(search_query: str) -> str:
    """Searches YouTube for a query and automatically clicks the first video result to start playback."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--autoplay-policy=no-user-gesture-required"]
        )
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        try:
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded")

            video_selector = "ytd-video-renderer a#video-title"
            await page.wait_for_selector(video_selector, timeout=10000)
            await page.click(video_selector)

            return f"Playing '{search_query}' on YouTube."
        except Exception as e:
            return f"Failed to play YouTube video: {e}"


def take_screenshot_sync(url: str, output_path: str = "screenshot.png") -> str:
    """Synchronous execution wrapper for take_screenshot."""
    return asyncio.run(take_screenshot(url, output_path))


def play_youtube_video_sync(search_query: str) -> str:
    """Synchronous execution wrapper for play_youtube_video."""
    return asyncio.run(play_youtube_video(search_query))


if __name__ == "__main__":
    print("[WebTools] Module loaded.")
