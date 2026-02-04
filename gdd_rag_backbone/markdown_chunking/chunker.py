"""
Main chunking logic for markdown files.

Implements document-based (structure-first) chunking with recursive fallback.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from gdd_rag_backbone.markdown_chunking.markdown_parser import MarkdownParser, MarkdownSection
from gdd_rag_backbone.markdown_chunking.metadata_extractor import MetadataExtractor
from gdd_rag_backbone.markdown_chunking.tokenizer_utils import count_tokens


@dataclass
class MarkdownChunk:
    """Represents a chunk of markdown content."""

    chunk_id: str
    doc_id: str
    content: str
    metadata: Dict[str, str]
    parent_header: Optional[str]
    part_number: Optional[int]  # For recursive splits: 1, 2, 3, etc.
    token_count: int


class MarkdownChunker:
    """Main chunker for markdown files."""

    def __init__(
        self,
        chunk_size_tokens: int = 800,
        chunk_overlap_tokens: int = 80,
        max_chunk_size: int = 1000,
    ):
        """
        Initialize chunker.

        Args:
            chunk_size_tokens: Target chunk size in tokens
            chunk_overlap_tokens: Overlap size in tokens (for recursive splits)
            max_chunk_size: Maximum chunk size before forcing recursive split
        """
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        self.max_chunk_size = max_chunk_size
        self.parser = MarkdownParser()
        self.metadata_extractor = MetadataExtractor()
        self.chunk_counter = 0

    def chunk_document(
        self, markdown_content: str, doc_id: str, filename: str = ""
    ) -> List[MarkdownChunk]:
        """
        Chunk a markdown document.

        Args:
            markdown_content: Full markdown content
            doc_id: Document ID
            filename: Original filename (for metadata)

        Returns:
            List of MarkdownChunk objects
        """
        self.chunk_counter = 0
        chunks: List[MarkdownChunk] = []

        # Extract document title
        document_title = self.parser.extract_document_title(markdown_content)
        doc_metadata = self.metadata_extractor.extract_document_metadata(document_title, filename)

        # Parse markdown into sections
        sections = self.parser.parse(markdown_content)

        # Process each section
        for section in sections:
            section_chunks = self._chunk_section(
                section=section,
                doc_id=doc_id,
                document_title=document_title,
                doc_metadata=doc_metadata,
            )
            chunks.extend(section_chunks)

        return chunks

    def _chunk_section(
        self,
        section: MarkdownSection,
        doc_id: str,
        document_title: str,
        doc_metadata: Dict[str, str],
    ) -> List[MarkdownChunk]:
        """
        Chunk a single section.

        Args:
            section: MarkdownSection to chunk
            doc_id: Document ID
            document_title: Document title
            doc_metadata: Document-level metadata

        Returns:
            List of chunks for this section
        """
        # Build full section content with header
        if section.header:
            full_content = f"## {section.header}\n\n{section.content}"
        else:
            full_content = section.content

        # Count tokens
        token_count = count_tokens(full_content)

        # If section fits in one chunk, return it
        if token_count <= self.chunk_size_tokens:
            return [
                self._create_chunk(
                    content=full_content,
                    doc_id=doc_id,
                    section_header=section.header,
                    section_content=section.content,
                    document_title=document_title,
                    doc_metadata=doc_metadata,
                    parent_header=None,
                    part_number=None,
                )
            ]

        # Section is too long - need to split
        # First, try splitting by sub-headers (### or numbered sections)
        sub_sections = self._split_by_subheaders(section)

        if len(sub_sections) > 1:
            # Successfully split by sub-headers
            chunks = []
            for sub_section in sub_sections:
                sub_chunks = self._chunk_section(
                    section=sub_section,
                    doc_id=doc_id,
                    document_title=document_title,
                    doc_metadata=doc_metadata,
                )
                chunks.extend(sub_chunks)
            return chunks

        # No sub-headers found - use recursive chunking
        return self._chunk_recursive(
            section=section, doc_id=doc_id, document_title=document_title, doc_metadata=doc_metadata
        )

    def _split_by_subheaders(self, section: MarkdownSection) -> List[MarkdownSection]:
        """
        Try to split section by sub-headers (### or numbered).

        Args:
            section: Section to split

        Returns:
            List of sub-sections, or [section] if no sub-headers found
        """
        # Look for ### headers or numbered sections (4.1, 4.2, etc.)
        content = section.content
        lines = content.split("\n")

        sub_sections: List[MarkdownSection] = []
        current_sub_content: List[str] = []
        current_sub_header: Optional[str] = None
        line_start = section.line_start

        for i, line in enumerate(lines):
            # Check for ### header
            h3_match = re.match(r"^###\s+(.+)$", line)
            # Check for numbered section in header format
            numbered_match = re.match(r"^#{2,}\s+(\d+\.\d+[\.\d]*)\s+(.+)$", line)

            if h3_match or numbered_match:
                # Save previous sub-section
                if current_sub_header is not None or current_sub_content:
                    sub_content = "\n".join(current_sub_content).strip()
                    if sub_content:
                        sub_sections.append(
                            MarkdownSection(
                                level=3,
                                header=current_sub_header or "",
                                content=sub_content,
                                line_start=line_start,
                                line_end=section.line_start + i - 1,
                                parent_header=section.header,
                            )
                        )

                # Start new sub-section
                if h3_match:
                    current_sub_header = h3_match.group(1).strip()
                else:
                    current_sub_header = numbered_match.group(2).strip()
                current_sub_content = []
                line_start = section.line_start + i
            else:
                current_sub_content.append(line)

        # Save last sub-section
        if current_sub_header is not None or current_sub_content:
            sub_content = "\n".join(current_sub_content).strip()
            if sub_content:
                sub_sections.append(
                    MarkdownSection(
                        level=3,
                        header=current_sub_header or "",
                        content=sub_content,
                        line_start=line_start,
                        line_end=section.line_end,
                        parent_header=section.header,
                    )
                )

        # If we found sub-sections, return them; otherwise return original
        if len(sub_sections) > 1:
            return sub_sections
        else:
            return [section]

    def _chunk_recursive(
        self,
        section: MarkdownSection,
        doc_id: str,
        document_title: str,
        doc_metadata: Dict[str, str],
    ) -> List[MarkdownChunk]:
        """
        Recursively chunk a long section.

        Splits in order: paragraphs -> list items -> sentences
        Applies overlap only at sentence/paragraph level.

        Args:
            section: Section to chunk
            doc_id: Document ID
            document_title: Document title
            doc_metadata: Document metadata

        Returns:
            List of chunks
        """
        chunks: List[MarkdownChunk] = []
        content = section.content
        parent_header = section.header

        # Try splitting by paragraphs first
        paragraphs = self.parser.split_by_paragraphs(content)

        if len(paragraphs) > 1:
            # Split by paragraphs with overlap
            current_chunk_parts: List[str] = []
            current_tokens = 0
            part_num = 1

            for i, para in enumerate(paragraphs):
                para_tokens = count_tokens(para)

                # If adding this paragraph would exceed limit
                if current_tokens + para_tokens > self.chunk_size_tokens and current_chunk_parts:
                    # Save current chunk
                    chunk_content = "\n\n".join(current_chunk_parts)
                    if parent_header:
                        chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

                    chunks.append(
                        self._create_chunk(
                            content=chunk_content,
                            doc_id=doc_id,
                            section_header=parent_header,
                            section_content=chunk_content,
                            document_title=document_title,
                            doc_metadata=doc_metadata,
                            parent_header=parent_header,
                            part_number=part_num,
                        )
                    )

                    # Start new chunk with overlap
                    overlap_text = self._get_overlap_text(
                        current_chunk_parts[-1] if current_chunk_parts else ""
                    )
                    current_chunk_parts = [overlap_text, para] if overlap_text else [para]
                    current_tokens = count_tokens("\n\n".join(current_chunk_parts))
                    part_num += 1
                else:
                    current_chunk_parts.append(para)
                    current_tokens += para_tokens

            # Save last chunk
            if current_chunk_parts:
                chunk_content = "\n\n".join(current_chunk_parts)
                if parent_header:
                    chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

                chunks.append(
                    self._create_chunk(
                        content=chunk_content,
                        doc_id=doc_id,
                        section_header=parent_header,
                        section_content=chunk_content,
                        document_title=document_title,
                        doc_metadata=doc_metadata,
                        parent_header=parent_header,
                        part_number=part_num,
                    )
                )

            return chunks

        # If paragraphs didn't work, try list items
        list_items = self.parser.split_by_list_items(content)

        if len(list_items) > 1:
            # Similar logic to paragraphs but for list items
            current_chunk_parts: List[str] = []
            current_tokens = 0
            part_num = 1

            for item in list_items:
                item_tokens = count_tokens(item)

                if current_tokens + item_tokens > self.chunk_size_tokens and current_chunk_parts:
                    chunk_content = "\n".join(current_chunk_parts)
                    if parent_header:
                        chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

                    chunks.append(
                        self._create_chunk(
                            content=chunk_content,
                            doc_id=doc_id,
                            section_header=parent_header,
                            section_content=chunk_content,
                            document_title=document_title,
                            doc_metadata=doc_metadata,
                            parent_header=parent_header,
                            part_number=part_num,
                        )
                    )

                    current_chunk_parts = [item]
                    current_tokens = item_tokens
                    part_num += 1
                else:
                    current_chunk_parts.append(item)
                    current_tokens += item_tokens

            if current_chunk_parts:
                chunk_content = "\n".join(current_chunk_parts)
                if parent_header:
                    chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

                chunks.append(
                    self._create_chunk(
                        content=chunk_content,
                        doc_id=doc_id,
                        section_header=parent_header,
                        section_content=chunk_content,
                        document_title=document_title,
                        doc_metadata=doc_metadata,
                        parent_header=parent_header,
                        part_number=part_num,
                    )
                )

            return chunks

        # Last resort: split by sentences
        sentences = self.parser.split_by_sentences(content)

        current_chunk_parts: List[str] = []
        current_tokens = 0
        part_num = 1

        for i, sentence in enumerate(sentences):
            sentence_tokens = count_tokens(sentence)

            if current_tokens + sentence_tokens > self.chunk_size_tokens and current_chunk_parts:
                chunk_content = " ".join(current_chunk_parts)
                if parent_header:
                    chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

                chunks.append(
                    self._create_chunk(
                        content=chunk_content,
                        doc_id=doc_id,
                        section_header=parent_header,
                        section_content=chunk_content,
                        document_title=document_title,
                        doc_metadata=doc_metadata,
                        parent_header=parent_header,
                        part_number=part_num,
                    )
                )

                # Start new chunk with overlap (last few sentences)
                overlap_sentences = self._get_overlap_sentences(current_chunk_parts)
                current_chunk_parts = overlap_sentences + [sentence]
                current_tokens = count_tokens(" ".join(current_chunk_parts))
                part_num += 1
            else:
                current_chunk_parts.append(sentence)
                current_tokens += sentence_tokens

        # Save last chunk
        if current_chunk_parts:
            chunk_content = " ".join(current_chunk_parts)
            if parent_header:
                chunk_content = f"## {parent_header} (Part {part_num})\n\n{chunk_content}"

            chunks.append(
                self._create_chunk(
                    content=chunk_content,
                    doc_id=doc_id,
                    section_header=parent_header,
                    section_content=chunk_content,
                    document_title=document_title,
                    doc_metadata=doc_metadata,
                    parent_header=parent_header,
                    part_number=part_num,
                )
            )

        return chunks

    def _get_overlap_text(self, text: str) -> str:
        """
        Get overlap text from end of previous chunk.

        Args:
            text: Text to extract overlap from

        Returns:
            Overlap text (approximately chunk_overlap_tokens)
        """
        if not text:
            return ""

        # Simple approach: take last N characters (approximate)
        # More sophisticated: take last sentences until we reach overlap token count
        sentences = self.parser.split_by_sentences(text)

        overlap_sentences = []
        overlap_tokens = 0

        # Take sentences from end until we reach overlap size
        for sentence in reversed(sentences):
            sentence_tokens = count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= self.chunk_overlap_tokens:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break

        return " ".join(overlap_sentences)

    def _get_overlap_sentences(self, sentences: List[str]) -> List[str]:
        """
        Get overlap sentences from end of previous chunk.

        Args:
            sentences: List of sentences

        Returns:
            List of overlap sentences
        """
        overlap_sentences = []
        overlap_tokens = 0

        for sentence in reversed(sentences):
            sentence_tokens = count_tokens(sentence)
            if overlap_tokens + sentence_tokens <= self.chunk_overlap_tokens:
                overlap_sentences.insert(0, sentence)
                overlap_tokens += sentence_tokens
            else:
                break

        return overlap_sentences

    def _create_chunk(
        self,
        content: str,
        doc_id: str,
        section_header: str,
        section_content: str,
        document_title: str,
        doc_metadata: Dict[str, str],
        parent_header: Optional[str],
        part_number: Optional[int],
    ) -> MarkdownChunk:
        """
        Create a MarkdownChunk object.

        Args:
            content: Chunk content
            doc_id: Document ID
            section_header: Section header
            section_content: Section content
            document_title: Document title
            doc_metadata: Document metadata
            parent_header: Parent header (for recursive splits)
            part_number: Part number (for recursive splits)

        Returns:
            MarkdownChunk object
        """
        self.chunk_counter += 1
        chunk_id = f"chunk_{self.chunk_counter:03d}"

        # Extract section metadata
        section_metadata = self.metadata_extractor.extract_section_metadata(
            section_header=section_header,
            section_content=section_content,
            document_title=document_title,
        )

        # Combine document and section metadata
        metadata = {**doc_metadata, **section_metadata}

        token_count = count_tokens(content)

        return MarkdownChunk(
            chunk_id=chunk_id,
            doc_id=doc_id,
            content=content,
            metadata=metadata,
            parent_header=parent_header,
            part_number=part_number,
            token_count=token_count,
        )
