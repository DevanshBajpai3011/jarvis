import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_path_shortcut(target: str) -> Path:
    """Resolves folder shortcuts (Desktop, Documents, Downloads, Projects) or returns expanded Path object."""
    user_home = Path.home()
    shortcuts = {
        "desktop": user_home / "Desktop",
        "downloads": user_home / "Downloads",
        "documents": user_home / "Documents",
        "pictures": user_home / "Pictures",
        "music": user_home / "Music",
        "videos": user_home / "Videos",
        "projects": user_home / "Projects"
    }
    clean_target = target.strip("\"'").lower()
    if clean_target in shortcuts:
        return shortcuts[clean_target]

    path_obj = Path(os.path.expanduser(target.strip("\"'")))
    parts = path_obj.parts
    if parts and parts[0].lower() in shortcuts:
        return shortcuts[parts[0].lower()].joinpath(*parts[1:])
    return path_obj.resolve()


def grep_files(query: str, target_dir: str = "Desktop", file_extension: str = None, max_results: int = 10) -> str:
    """
    Searches inside text files (.py, .txt, .md, .json, .log, .csv) within target_dir for lines matching `query`.

    Args:
        query: String or regex pattern to search for inside file contents.
        target_dir: Directory or shortcut ('Desktop', 'Documents', 'Downloads', 'C:/Projects').
        file_extension: Optional extension filter (e.g., '.py', '.txt').
        max_results: Max file matches to return.
    """
    try:
        search_path = resolve_path_shortcut(target_dir)
        if not search_path.exists():
            return f"Directory '{search_path}' does not exist."

        matches = []
        pattern = re.compile(query, re.IGNORECASE)
        ignore_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv", "build", "dist"}

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                if file_extension and not file.endswith(file_extension):
                    continue

                file_path = Path(root) / file

                # Exclude large binary/media files (> 5MB)
                if file_path.stat().st_size > 5 * 1024 * 1024:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern.search(line):
                                matches.append(f"[MATCH] {file_path} (Line {line_num}): {line.strip()[:90]}")
                                break  # Match found in this file
                except Exception:
                    continue

                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

        if not matches:
            return f"No matches found for content query '{query}' inside '{search_path}'."

        return f"Found {len(matches)} matching file(s):\n" + "\n".join(matches)

    except Exception as e:
        return f"Grep search failed: {e}"


def search_files_by_name(filename_pattern: str, target_dir: str = "Desktop", max_results: int = 10) -> str:
    """Fuzzy searches for filenames or extensions inside target_dir."""
    try:
        search_path = resolve_path_shortcut(target_dir)
        if not search_path.exists():
            return f"Directory '{search_path}' does not exist."

        matches = []
        pattern = filename_pattern.lower()
        ignore_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv"}

        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                if pattern in file.lower():
                    matches.append(str(Path(root) / file))
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        if not matches:
            return f"No files matching '{filename_pattern}' found in '{search_path}'."

        return f"Found {len(matches)} file(s):\n" + "\n".join(matches)

    except Exception as e:
        return f"File search failed: {e}"


if __name__ == "__main__":
    print("[FileSearch] Module loaded.")
