import logging

logger = logging.getLogger(__name__)

try:
    from ddgs import DDGS
    HAS_DDG = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDG = True
    except ImportError:
        HAS_DDG = False


def search_web(query: str) -> str:
    """
    Performs a live web search using DuckDuckGo to fetch news, current facts, and real-time internet information.

    Args:
        query (str): The search query text.

    Returns:
        str: Summary of top web search results.
    """
    if not query or not query.strip():
        return "No search query provided, sir."

    query_clean = query.strip()
    logger.info(f"[Web Search] Searching live web for: '{query_clean}'")

    if not HAS_DDG:
        return "Web search library is currently unavailable on this system, sir."

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query_clean, max_results=5))

        if not results:
            return f"No search results found for '{query_clean}', sir."

        snippets = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            href = r.get("href", "").strip()
            if title and body:
                snippets.append(f"{i}. {title}: {body} (Source: {href})")

        if not snippets:
            return f"No valid search snippets retrieved for '{query_clean}', sir."

        header = f"Live Web Search Results for '{query_clean}':\n"
        return header + "\n\n".join(snippets)
    except Exception as e:
        logger.error(f"[Web Search Error] {e}")
        return f"Web search encountered an issue: {str(e)}"


if __name__ == "__main__":
    print("[Web Search Test]:")
    print(search_web("latest tech news"))
