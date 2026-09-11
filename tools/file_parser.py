import os
import logging
from typing import Dict, Any
import pypdf
from PIL import Image

logger = logging.getLogger(__name__)


class FileParser:
    """
    Handles reading and parsing various file formats including PDFs, images,
    source code, and text documents.
    """

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
    TEXT_EXTENSIONS = {
        ".py", ".js", ".txt", ".md", ".json", ".csv",
        ".cpp", ".c", ".java"
    }

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parses the specified file based on its extension.

        Returns a dictionary with keys 'type' and 'content'.
        - For PDF / Text / Code: {"type": "text", "content": <extracted_text>}
        - For Image: {"type": "image", "content": <file_path>}
        - For Error / Unsupported: {"type": "error", "content": <error_message>}
        """
        if not os.path.exists(file_path):
            return {"type": "error", "content": f"File not found: {file_path}"}

        if not os.path.isfile(file_path):
            return {"type": "error", "content": f"Path is not a file: {file_path}"}

        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        try:
            if ext == ".pdf":
                return self._parse_pdf(file_path)
            elif ext in self.IMAGE_EXTENSIONS:
                return self._parse_image(file_path)
            elif ext in self.TEXT_EXTENSIONS:
                return self._parse_text(file_path)
            else:
                return {"type": "error", "content": "Unsupported file format."}
        except PermissionError:
            return {"type": "error", "content": f"Permission denied accessing file: {file_path}"}
        except Exception as e:
            logger.error(f"Error parsing file '{file_path}': {e}")
            return {"type": "error", "content": f"Error reading file: {str(e)}"}

    def _parse_pdf(self, file_path: str) -> Dict[str, Any]:
        reader = pypdf.PdfReader(file_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        extracted = "\n".join(pages_text)
        return {"type": "text", "content": extracted}

    def _parse_image(self, file_path: str) -> Dict[str, Any]:
        with Image.open(file_path) as img:
            img.verify()
        return {"type": "image", "content": file_path}

    def _parse_text(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"type": "text", "content": content}
