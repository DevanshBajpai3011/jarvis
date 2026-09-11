import os
import subprocess
import difflib
import logging

logger = logging.getLogger(__name__)


def find_and_open_folder(folder_name: str) -> str:
    """
    Locates a system directory by alias, exact match, or fuzzy matching across common
    user profile folders and drive locations, and opens it using Windows File Explorer.

    Args:
        folder_name (str): Target folder name or alias (e.g. 'Downloads', 'Projects', 'Documents').

    Returns:
        str: Confirmation or error status message.
    """
    if not folder_name or not folder_name.strip():
        return "Please specify a folder name to open."

    clean_name = folder_name.strip().lower()
    user_home = os.path.expanduser("~")

    # Standard system directory aliases map
    standard_aliases = {
        "downloads": os.path.join(user_home, "Downloads"),
        "download": os.path.join(user_home, "Downloads"),
        "documents": os.path.join(user_home, "Documents"),
        "docs": os.path.join(user_home, "Documents"),
        "desktop": os.path.join(user_home, "Desktop"),
        "pictures": os.path.join(user_home, "Pictures"),
        "photos": os.path.join(user_home, "Pictures"),
        "videos": os.path.join(user_home, "Videos"),
        "movies": os.path.join(user_home, "Videos"),
        "music": os.path.join(user_home, "Music"),
        "audio": os.path.join(user_home, "Music"),
        "projects": r"e:\Projects" if os.path.exists(r"e:\Projects") else os.path.join(user_home, "Projects"),
        "project": r"e:\Projects" if os.path.exists(r"e:\Projects") else os.path.join(user_home, "Projects"),
        "jarvis": r"e:\Projects\J.A.R.V.I.S\jarvis" if os.path.exists(r"e:\Projects\J.A.R.V.I.S\jarvis") else os.path.join(user_home, "jarvis"),
    }

    target_path = None

    # 1. Direct alias match check
    if clean_name in standard_aliases:
        alias_path = standard_aliases[clean_name]
        if os.path.exists(alias_path):
            target_path = alias_path

    # 2. Check if clean_name is an absolute path or relative path that exists
    if not target_path and os.path.exists(folder_name.strip()):
        target_path = os.path.abspath(folder_name.strip())

    # 3. Dynamic sub-directory search across primary drive & user profile locations
    if not target_path:
        search_roots = [
            user_home,
            r"e:\Projects",
            r"C:\\",
            r"D:\\",
            r"E:\\",
        ]

        candidate_paths = {}
        for root in search_roots:
            if not os.path.exists(root):
                continue
            try:
                for entry in os.listdir(root):
                    full_path = os.path.join(root, entry)
                    if os.path.isdir(full_path):
                        candidate_paths[entry.lower()] = full_path
            except PermissionError:
                continue
            except Exception as e:
                logger.debug(f"[FolderFinder] Error scanning {root}: {e}")

        # Check exact name in candidate directories
        if clean_name in candidate_paths:
            target_path = candidate_paths[clean_name]
        else:
            # Fuzzy match candidates
            matches = difflib.get_close_matches(clean_name, list(candidate_paths.keys()), n=1, cutoff=0.5)
            if matches:
                target_path = candidate_paths[matches[0]]

    if target_path and os.path.exists(target_path):
        try:
            if hasattr(os, "startfile"):
                os.startfile(target_path)
            else:
                subprocess.Popen(["explorer", target_path])
            logger.info(f"[FolderFinder] Successfully opened folder: {target_path}")
            return f"Successfully opened directory: {target_path}"
        except Exception as e:
            logger.error(f"[FolderFinder Error] Failed to open folder '{target_path}': {e}")
            return f"Found directory at '{target_path}', but failed to open Explorer: {e}"

    return f"Could not locate folder '{folder_name}' on the system."


if __name__ == "__main__":
    res = find_and_open_folder("Downloads")
    print("Test Result:", res)
