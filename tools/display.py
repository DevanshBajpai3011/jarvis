import logging

logger = logging.getLogger(__name__)


def display_content(title: str, markdown_content: str) -> str:
    """
    Displays rich visual content (recipes, code snippets, lists, tabular data) on the J.A.R.V.I.S. desktop overlay screen.

    Args:
        title (str): Title or headline of the visual display card.
        markdown_content (str): Rich markdown formatted text or table data to show on screen.

    Returns:
        str: Confirmation message that content was rendered to the user's screen.
    """
    logger.info(f"[DisplayTool] Rendering visual card '{title}' with content length {len(markdown_content)}")
    return "Content successfully displayed on user screen."
