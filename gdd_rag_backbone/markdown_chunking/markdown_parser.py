"""
Markdown parser for extracting structure and sections.

Parses markdown files to identify headers, sections, and content hierarchy.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class MarkdownSection:
    """Represents a section in a markdown document."""

    level: int  # Header level (1 for ##, 2 for ###, etc.)
    header: str  # Header text (without # symbols)
    content: str  # Section content (everything until next header)
    line_start: int  # Starting line number
    line_end: int  # Ending line number
    parent_header: Optional[str] = None  # Parent section header if nested


class MarkdownParser:
    """Parser for markdown files to extract structure."""

    def __init__(self):
        # Pattern to match headers: ## Header or ### Header
        self.header_pattern = re.compile(r"^(#{2,})\s+(.+)$", re.MULTILINE)
        # Pattern to match numbered sections: 4.1, 5.2, etc.
        self.numbered_section_pattern = re.compile(
            r"^#{2,}\s+(\d+\.\d+[\.\d]*)\s+(.+)$", re.MULTILINE
        )

    def parse(self, markdown_content: str) -> List[MarkdownSection]:
        """
        Parse markdown content into sections.

        Args:
            markdown_content: Full markdown content as string

        Returns:
            List of MarkdownSection objects
        """
        lines = markdown_content.split("\n")
        sections: List[MarkdownSection] = []

        current_section: Optional[MarkdownSection] = None
        current_content: List[str] = []
        # Stack to track (level, header) pairs
        parent_stack: List[Tuple[int, str]] = []

        for i, line in enumerate(lines):
            # Check if this line is a header
            header_match = self.header_pattern.match(line)

            if header_match:
                # Save previous section if exists
                if current_section is not None:
                    current_section.content = "\n".join(current_content).strip()
                    current_section.line_end = i - 1
                    sections.append(current_section)

                # Extract header level and text
                header_level = len(header_match.group(1))
                header_text = header_match.group(2).strip()

                # Update parent stack based on level
                # Remove parents at same or deeper level
                parent_stack = [(lvl, hdr) for lvl, hdr in parent_stack if lvl < header_level]

                # Determine parent header (last header at shallower level)
                parent_header = parent_stack[-1][1] if parent_stack else None

                # Add to parent stack
                parent_stack.append((header_level, header_text))

                # Start new section
                current_section = MarkdownSection(
                    level=header_level,
                    header=header_text,
                    content="",
                    line_start=i,
                    line_end=i,
                    parent_header=parent_header,
                )
                current_content = []
            else:
                # Add line to current section content
                if current_section is not None:
                    current_content.append(line)
                elif not sections:
                    # Content before first header - create a pseudo-section
                    current_content.append(line)

        # Save last section
        if current_section is not None:
            current_section.content = "\n".join(current_content).strip()
            current_section.line_end = len(lines) - 1
            sections.append(current_section)
        elif current_content:
            # No headers found, create a single section with all content
            sections.append(
                MarkdownSection(
                    level=0,
                    header="",
                    content="\n".join(current_content).strip(),
                    line_start=0,
                    line_end=len(lines) - 1,
                    parent_header=None,
                )
            )

        return sections

    def extract_document_title(self, markdown_content: str) -> str:
        """
        Extract document title from markdown.

        Looks for first ## header or uses filename.

        Args:
            markdown_content: Full markdown content

        Returns:
            Document title
        """
        sections = self.parse(markdown_content)
        if sections and sections[0].header:
            return sections[0].header
        return "Untitled Document"

    def split_by_paragraphs(self, content: str) -> List[str]:
        """
        Split content by paragraph boundaries (double newlines).

        Args:
            content: Content to split

        Returns:
            List of paragraphs
        """
        paragraphs = re.split(r"\n\s*\n", content)
        return [p.strip() for p in paragraphs if p.strip()]

    def split_by_sentences(self, content: str) -> List[str]:
        """
        Split content by sentence boundaries.

        Args:
            content: Content to split

        Returns:
            List of sentences
        """
        # Split on sentence endings: . ! ? followed by space or newline
        sentences = re.split(r"([.!?])\s+", content)
        # Rejoin sentence endings with their sentences
        result = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                result.append(sentences[i] + sentences[i + 1])
            else:
                result.append(sentences[i])
        if len(sentences) % 2 == 1:
            result.append(sentences[-1])
        return [s.strip() for s in result if s.strip()]

    def split_by_list_items(self, content: str) -> List[str]:
        """
        Split content by bullet list items.

        Args:
            content: Content to split

        Returns:
            List of list items (with their bullets)
        """
        # Match lines starting with - or * or numbered lists
        lines = content.split("\n")
        items = []
        current_item = []

        for line in lines:
            # Check if line is a list item
            if re.match(r"^\s*[-*]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
                if current_item:
                    items.append("\n".join(current_item).strip())
                current_item = [line]
            else:
                if current_item:
                    current_item.append(line)
                else:
                    # Non-list content - treat as separate item
                    if line.strip():
                        items.append(line.strip())

        if current_item:
            items.append("\n".join(current_item).strip())

        return [item for item in items if item]
