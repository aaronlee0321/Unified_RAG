"""
Metadata extraction for markdown chunks.

Extracts document_title, section_header, screen, content_type, and language.
"""

import re
from typing import Dict


class MetadataExtractor:
    """Extract metadata from markdown sections."""

    def __init__(self):
        # Patterns for detecting content types
        self.table_pattern = re.compile(r"\|.*\|", re.MULTILINE)  # Markdown table
        self.flow_pattern = re.compile(r"userflow|flow|user\s+flow", re.IGNORECASE)
        self.logic_pattern = re.compile(r"logic|sort|algorithm", re.IGNORECASE)
        self.note_pattern = re.compile(r"note:|note\s*:", re.IGNORECASE)

        # Patterns for detecting screen names
        self.garage_pattern = re.compile(r"garage|tank\s+garage", re.IGNORECASE)
        self.decor_pattern = re.compile(r"decor|decoration", re.IGNORECASE)
        self.custom_pattern = re.compile(r"custom", re.IGNORECASE)

    def extract_document_metadata(self, document_title: str, filename: str) -> Dict[str, str]:
        """
        Extract document-level metadata.

        Args:
            document_title: Title extracted from markdown
            filename: Original filename

        Returns:
            Dictionary with document metadata
        """
        return {
            "document_title": document_title or self._extract_title_from_filename(filename),
            "language": self._detect_language(document_title + " " + filename),
        }

    def extract_section_metadata(
        self, section_header: str, section_content: str, document_title: str = ""
    ) -> Dict[str, str]:
        """
        Extract metadata for a section.

        Args:
            section_header: Section header text
            section_content: Section content
            document_title: Document title for context

        Returns:
            Dictionary with section metadata
        """
        (section_header + " " + section_content).lower()

        return {
            "section_header": section_header,
            "screen": self._detect_screen(section_header, section_content),
            "content_type": self._detect_content_type(section_content, section_header),
            "language": self._detect_language(section_header + " " + section_content),
        }

    def _detect_screen(self, header: str, content: str) -> str:
        """
        Detect screen name from header and content.

        Args:
            header: Section header
            content: Section content

        Returns:
            Screen name: "Garage", "TankDecor", "Custom", or "Unknown"
        """
        text = (header + " " + content).lower()

        if self.custom_pattern.search(text):
            return "Custom"
        elif self.decor_pattern.search(text):
            return "TankDecor"
        elif self.garage_pattern.search(text):
            return "Garage"
        else:
            return "Unknown"

    def _detect_content_type(self, content: str, header: str = "") -> str:
        """
        Detect content type from content and header.

        Args:
            content: Section content
            header: Section header (optional)

        Returns:
            Content type: "table", "flow", "logic", "note", or "ui"
        """
        combined = (header + " " + content).lower()

        # Check in order of specificity
        if self.table_pattern.search(content):
            return "table"
        elif self.flow_pattern.search(combined):
            return "flow"
        elif self.logic_pattern.search(combined):
            return "logic"
        elif self.note_pattern.search(combined):
            return "note"
        else:
            return "ui"

    def _detect_language(self, text: str) -> str:
        """
        Detect language from text.

        Simple heuristic: if text contains Vietnamese characters, assume "vi"
        Otherwise default to "en"

        Args:
            text: Text to analyze

        Returns:
            Language code: "vi" or "en"
        """
        # Check for Vietnamese characters (common diacritics)
        vietnamese_chars = re.compile(
            r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE
        )

        if vietnamese_chars.search(text):
            return "vi"
        else:
            return "en"

    def _extract_title_from_filename(self, filename: str) -> str:
        """
        Extract title from filename.

        Args:
            filename: Filename (with or without path)

        Returns:
            Extracted title
        """
        # Remove path and extension
        import os

        name = os.path.basename(filename)
        name = os.path.splitext(name)[0]

        # Clean up common patterns
        name = name.replace("[", "").replace("]", "")
        name = name.replace("_", " ").replace("-", " ")

        return name.strip()
