import os
import re
import urllib.parse
import webbrowser
import subprocess
import logging

logger = logging.getLogger(__name__)


def open_web_target(query_or_url: str, platform: str = "general") -> str:
    """
    Navigates to a website, opens a web search, or plays media on YouTube in the default browser/Chrome.

    Args:
        query_or_url (str): Target URL, domain, search query, or video name.
        platform (str): Platform target ('general', 'youtube', 'google'). Default is 'general'.

    Returns:
        str: Confirmation message with target URL.
    """
    if not query_or_url or not query_or_url.strip():
        return "Please specify a URL, website, or search query to navigate."

    clean_input = query_or_url.strip()
    platform_lower = (platform or "general").strip().lower()

    # Detect YouTube playback requests
    is_youtube = (
        platform_lower == "youtube"
        or "youtube" in clean_input.lower()
        or clean_input.lower().startswith("play ")
    )

    if is_youtube:
        # Strip common action preambles
        search_term = re.sub(
            r"^(play|search for|open|go to)\s+|(on youtube|in youtube|youtube)$",
            "",
            clean_input,
            flags=re.IGNORECASE,
        ).strip()

        if not search_term:
            search_term = clean_input

        target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_term)}"
    else:
        # Check if input is a valid URL or domain (e.g., github.com, reddit.com, https://...)
        domain_pattern = r"^(https?://)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(/.*)?$"
        if re.match(domain_pattern, clean_input):
            if not clean_input.startswith(("http://", "https://")):
                target_url = f"https://{clean_input}"
            else:
                target_url = clean_input
        else:
            # Default to Google Search
            target_url = f"https://www.google.com/search?q={urllib.parse.quote(clean_input)}"

    # Attempt launching via Google Chrome executable if available on Windows
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]

    chrome_launched = False
    for path in chrome_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path, target_url])
                chrome_launched = True
                logger.info(f"[BrowserAutomation] Launched Chrome executable for URL: {target_url}")
                break
            except Exception as e:
                logger.warning(f"[BrowserAutomation] Chrome launch attempt failed: {e}")

    if not chrome_launched:
        try:
            webbrowser.open(target_url)
            logger.info(f"[BrowserAutomation] Opened URL via default browser: {target_url}")
        except Exception as e:
            logger.error(f"[BrowserAutomation Error] Failed to open browser: {e}")
            return f"Failed to open browser for '{target_url}': {e}"

    return f"Successfully navigated to {target_url}"


if __name__ == "__main__":
    res = open_web_target("github.com")
    print("Test Result:", res)
