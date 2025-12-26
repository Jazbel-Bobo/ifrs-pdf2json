"""Multiple parsing strategies for extracting structure from PDF text."""

import re
from typing import List, Tuple, Optional, Dict
from pdf2json.models import (
    StandardDocument, StandardTitle, MainContent, Section, Subsection,
    Paragraph, Clause, Table, Footnote, Definition, Exclusions, Exclusion,
    Appendix
)
from pdf2json.parser import PDFTextExtractor
from typing import Any


# Hebrew to Latin letter mapping for paragraph suffixes
HEBREW_TO_LATIN: Dict[str, str] = {
    'א': 'A', 'ב': 'B', 'ג': 'C', 'ד': 'D', 'ה': 'E',
    'ו': 'V', 'ז': 'Z', 'ח': 'H', 'ט': 'T', 'י': 'I',
    'כ': 'K', 'ל': 'L', 'מ': 'M', 'נ': 'N', 'ס': 'S',
    'ע': 'O', 'פ': 'P', 'צ': 'Q', 'ק': 'Q', 'ר': 'R',
    'ש': 'SH', 'ת': 'TH'
}

def hebrew_to_latin(hebrew_char: str) -> str:
    """Convert Hebrew letter to Latin equivalent for paragraph IDs."""
    return HEBREW_TO_LATIN.get(hebrew_char, hebrew_char)


class ParsingStrategy:
    """Base class for parsing strategies."""
    
    def parse(self, extractor: PDFTextExtractor, standard_id: str) -> Tuple[StandardDocument, float]:
        """Parse PDF and return structured document with confidence score.
        
        Args:
            extractor: PDFTextExtractor instance
            standard_id: Standard identifier (e.g., "IAS_16")
            
        Returns:
            Tuple of (StandardDocument, confidence_score)
        """
        raise NotImplementedError


class SimpleStrategy(ParsingStrategy):
    """Simple parsing strategy using basic heuristics."""
    
    def parse(self, extractor: PDFTextExtractor, standard_id: str) -> Tuple[StandardDocument, float]:
        """Parse using simple pattern matching."""
        # Extract positioned lines for better paragraph detection
        positioned_lines = extractor.extract_positioned_lines()
        baseline_text = extractor.extract_baseline_text()
        
        # Extract standard title and ID from page 1
        page1_lines = [line for line in positioned_lines if line["page"] == 1]
        title_hebrew, title_english, extracted_standard_id = self._extract_title_from_page1(page1_lines)
        
        # Use extracted standard_id if found, otherwise use provided one
        if extracted_standard_id:
            standard_id = extracted_standard_id
        
        standard_title = StandardTitle(hebrew=title_hebrew, english=title_english)
        
        # Detect TOC and main content boundaries
        main_start_index = self._detect_main_content_start(positioned_lines)
        
        # Split content into main body and appendices
        main_lines, appendix_lines_dict = self._split_main_and_appendices(
            positioned_lines[main_start_index:] if main_start_index > 0 else positioned_lines
        )
        
        # Parse main content from positioned lines (excluding front matter and TOC)
        main_content = self._parse_main_content_from_lines(main_lines, standard_id)
        
        # Parse appendices
        appendix_A = None
        appendix_B = None
        appendix_C = None
        
        if 'A' in appendix_lines_dict:
            appendix_A = self._parse_appendix(appendix_lines_dict['A'], standard_id, 'A')
        if 'B' in appendix_lines_dict:
            appendix_B = self._parse_appendix(appendix_lines_dict['B'], standard_id, 'B')
        if 'C' in appendix_lines_dict:
            appendix_C = self._parse_appendix(appendix_lines_dict['C'], standard_id, 'C')
        
        # Extract structured text (needed for both exclusions and definitions)
        structured_text = extractor.extract_text_with_structure()
        
        # Extract exclusions (look for untranslated markers)
        exclusions = self._extract_exclusions(structured_text)
        
        # Create document first (needed for definition extraction)
        document = StandardDocument(
            standard_id=standard_id,
            standard_title=standard_title,
            main=main_content,
            appendix_A=appendix_A,
            appendix_B=appendix_B,
            appendix_C=appendix_C,
            definitions=[],  # Will be populated below
            exclusions=exclusions
        )
        
        # Now extract definitions from "הגדרות" section (paragraph 6) or Appendix A
        definitions = self._extract_definitions(structured_text, standard_id, document)
        document.definitions = definitions
        
        # Calculate confidence (basic heuristic)
        confidence = self._calculate_confidence(document, baseline_text)
        
        return document, confidence
    
    def _extract_title_from_page1(self, page1_lines: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Extract title from page 1 text blocks.
        
        Returns:
            Tuple of (hebrew_title, english_title, standard_id)
        """
        if not page1_lines:
            return None, None, None
        
        # Get all text from page 1
        page1_text = "\n".join([line["text"] for line in page1_lines])
        
        # Extract Hebrew title: "תקן חשבונאות בינלאומי\s+(\d+)" + next meaningful Hebrew line
        hebrew_pattern = re.compile(r'תקן\s+חשבונאות\s+בינלאומי\s+(\d+)', re.IGNORECASE)
        hebrew_match = hebrew_pattern.search(page1_text)
        
        hebrew_title = None
        standard_number = None
        
        if hebrew_match:
            standard_number = hebrew_match.group(1)
            # Find the next meaningful Hebrew line after the standard number
            # Look in page1_lines for better accuracy
            match_line_idx = None
            for idx, line in enumerate(page1_lines):
                if hebrew_pattern.search(line["text"]):
                    match_line_idx = idx
                    break
            
            subject = None
            if match_line_idx is not None:
                # Look at next few lines for the subject (e.g., "רכוש קבוע")
                for idx in range(match_line_idx + 1, min(match_line_idx + 5, len(page1_lines))):
                    line_text = page1_lines[idx]["text"].strip()
                    # Check if it's a Hebrew subject line (2-4 words, all Hebrew)
                    if re.match(r'^[א-ת\s]{4,30}$', line_text) and len(line_text.split()) <= 4:
                        # Skip if it's just numbers or very short
                        if len(line_text) > 3 and not line_text.isdigit():
                            subject = line_text
                            break
            
            # Always include the number in Hebrew title
            if subject:
                hebrew_title = f"תקן חשבונאות בינלאומי {standard_number} {subject}"
            else:
                hebrew_title = f"תקן חשבונאות בינלאומי {standard_number}"
        
        # Extract English title: "International Accounting Standard\s+(\d+)" + next meaningful English line
        english_pattern = re.compile(r'International\s+Accounting\s+Standard\s+(\d+)', re.IGNORECASE)
        english_match = english_pattern.search(page1_text)
        
        english_title = None
        
        if english_match:
            if not standard_number:
                standard_number = english_match.group(1)
            
            # Find the next meaningful English line after the standard number
            # Look in the lines following the match, not just in remaining text
            match_line_idx = None
            for idx, line in enumerate(page1_lines):
                if english_pattern.search(line["text"]):
                    match_line_idx = idx
                    break
            
            subject = None
            subject_parts = []
            if match_line_idx is not None:
                # Look at next few lines for the subject (may be wrapped across lines)
                # Pattern: "Property, Plant and Equipment" - title case words
                for idx in range(match_line_idx + 1, min(match_line_idx + 6, len(page1_lines))):
                    line_text = page1_lines[idx]["text"].strip()
                    # Skip empty lines
                    if not line_text:
                        continue
                    # Check if line contains title case words (subject line)
                    # Accept lines that are title case words (may be comma-separated)
                    if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*$', line_text):
                        # Skip header words
                        skip_words = ["International", "Accounting", "Standard", "Financial", "Reporting"]
                        if not any(word in line_text for word in skip_words):
                            subject_parts.append(line_text)
                    # Also accept single title case words that might be part of a multi-line subject
                    elif re.match(r'^[A-Z][a-z]+$', line_text) and len(line_text) > 3:
                        skip_words = ["International", "Accounting", "Standard", "Financial", "Reporting", "The"]
                        if not any(word == line_text for word in skip_words):
                            subject_parts.append(line_text)
                
                # Join subject parts (handle wrapped lines like "Property, Plant" / "and Equipment")
                if subject_parts:
                    subject = " ".join(subject_parts)
                    # Clean up: remove extra spaces around commas
                    subject = re.sub(r'\s*,\s*', ', ', subject)
            
            # Fallback: search in remaining text if not found in lines
            if not subject:
                match_end = english_match.end()
                remaining_text = page1_text[match_end:]
                # Look for "Property, Plant and Equipment" pattern
                # Try to find title case words that form the subject
                english_subject_pattern = re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5}(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)', re.MULTILINE)
                subject_matches = english_subject_pattern.findall(remaining_text[:1000])
                
                for match in subject_matches:
                    text = match.strip()
                    # Skip if it's too short or looks like a header
                    if (len(text) > 10 and 
                        text not in ["International", "Accounting", "Standard"] and
                        "International" not in text and
                        "Accounting" not in text and
                        "Financial" not in text):
                        subject = text
                        break
            
            if subject:
                english_title = f"International Accounting Standard {standard_number} {subject}"
            else:
                english_title = f"International Accounting Standard {standard_number}"
        
        # Extract standard_id
        extracted_standard_id = None
        if standard_number:
            # Try to determine if it's IAS or IFRS from context
            if "IFRS" in page1_text.upper() or "International Financial Reporting Standard" in page1_text:
                extracted_standard_id = f"IFRS_{standard_number}"
            else:
                extracted_standard_id = f"IAS_{standard_number}"
        
        return hebrew_title, english_title, extracted_standard_id
    
    def _detect_main_content_start(self, positioned_lines: List[Dict[str, Any]]) -> int:
        """Detect where main content starts (after front matter and TOC).
        
        Returns:
            Index of first line that is part of main content
        """
        # Pattern for TOC: "תוכן עניינים"
        toc_pattern = re.compile(r'תוכן\s+עניינים', re.IGNORECASE)
        
        # Pattern for main content heading: "מטרת התקן"
        main_heading_pattern = re.compile(r'מטרת\s+התקן', re.IGNORECASE)
        
        # PRIMARY pattern: number-dot format (NUMBER. or NUMBERLETTER.)
        # Examples: "1.", "5.", "16.", "20א.", "81יד." (dot comes AFTER number/letters)
        # Space after dot is optional (may be stripped by PDF extraction)
        para_pattern_number_dot = re.compile(r'^(\d+)([א-ת]+)?\.\s*')  # Primary: "1.", "5.", "16.", "20א."
        para_pattern_one_dot = re.compile(r'^\s*1\.\s*$')  # "1." on its own line - highest priority for first paragraph
        
        # FALLBACK patterns for other PDF formats
        para_pattern_dot_number = re.compile(r'^\.(\d+)([א-ת]+)?\s+')  # ".16", ".20א" (dot before number)
        para_pattern_dot_one = re.compile(r'^\.1\s+')  # ".1 " - fallback
        para_pattern_one = re.compile(r'^\s*1\s+')  # "1 " - fallback
        
        toc_pages = set()
        main_start_index = None  # Use None to indicate not found yet
        found_heading = False
        
        # Find TOC pages - HARD EXCLUDE: mark ALL pages that contain TOC
        for i, line in enumerate(positioned_lines):
            if toc_pattern.search(line["text"]):
                toc_pages.add(line["page"])
                # Also mark subsequent pages if TOC spans multiple pages
                # (heuristic: if TOC found, mark next 2 pages as potentially TOC)
                for p in range(line["page"], min(line["page"] + 3, 100)):
                    toc_pages.add(p)
        
        # Also exclude page 1 (cover page) from main content
        cover_page = 1
        toc_pages.add(cover_page)
        
        # Find first non-TOC page as fallback start
        first_non_toc_index = None
        for i, line in enumerate(positioned_lines):
            if line["page"] not in toc_pages:
                first_non_toc_index = i
                break
        
        # Find main content start
        for i, line in enumerate(positioned_lines):
            # Skip if still in TOC pages
            if line["page"] in toc_pages:
                continue
            
            # Check for main heading "מטרת התקן"
            if main_heading_pattern.search(line["text"]):
                found_heading = True
                main_start_index = i
                # Continue to find the first paragraph after the heading
                continue
            
            # If we found the heading, look for the first paragraph
            if found_heading:
                # Look for paragraph 1 specifically first ("1. " is the primary pattern)
                if para_pattern_one_dot.match(line["text"]):
                    main_start_index = i
                    break
                # Also accept other number-dot patterns if heading was found
                elif para_pattern_number_dot.match(line["text"]):
                    # Check it's a low number (likely paragraph 1-5)
                    match = para_pattern_number_dot.match(line["text"])
                    if match:
                        para_num = int(match.group(1))
                        if para_num <= 5:
                            main_start_index = i
                            break
                # Fallback: dot-number patterns (for other PDF formats)
                elif para_pattern_dot_one.match(line["text"]):
                    main_start_index = i
                    break
                elif para_pattern_dot_number.match(line["text"]):
                    match = para_pattern_dot_number.match(line["text"])
                    if match:
                        para_num = int(match.group(1))
                        if para_num <= 5:
                            main_start_index = i
                            break
                # Fallback: plain number
                elif para_pattern_one.match(line["text"]) and len(line["text"].strip()) > 2:
                    main_start_index = i
                    break
            else:
                # If no heading found yet, look for paragraph 1 as start indicator
                if para_pattern_one_dot.match(line["text"]):
                    main_start_index = i
                    break
                # Also check for other early paragraphs ("2.", "3.", "5.", etc.) on first body page
                elif para_pattern_number_dot.match(line["text"]):
                    match = para_pattern_number_dot.match(line["text"])
                    if match:
                        para_num = int(match.group(1))
                        if para_num <= 5:  # Early paragraph
                            main_start_index = i
                            break
                # Also check for separate-line format: "1" followed by "." on next line
                elif i + 1 < len(positioned_lines):
                    next_line_text = positioned_lines[i + 1]["text"].strip()
                    current_line_text = line["text"].strip()
                    if current_line_text == "1" and next_line_text == ".":
                        # Check if line after "." has content
                        if i + 2 < len(positioned_lines):
                            content_line = positioned_lines[i + 2]["text"].strip()
                            if content_line and len(content_line) > 2:
                                main_start_index = i
                                break
                # Fallback: dot-number patterns
                elif para_pattern_dot_one.match(line["text"]):
                    main_start_index = i
                    break
                elif para_pattern_dot_number.match(line["text"]):
                    match = para_pattern_dot_number.match(line["text"])
                    if match:
                        para_num = int(match.group(1))
                        if para_num <= 5:  # Early paragraph
                            main_start_index = i
                            break
        
        # If we didn't find a specific start, use first non-TOC page as fallback
        if main_start_index is None:
            main_start_index = first_non_toc_index if first_non_toc_index is not None else 0
        
        return main_start_index
    
    def _detect_paragraph_start(self, line_text: str) -> Optional[Tuple[str, str, str]]:
        """Detect if a line starts with a paragraph number token.
        
        Primary pattern: NUMBER. or NUMBERLETTER. (dot comes AFTER number/letters).
        Examples: "5.", "81.", "81א.", "81יד." (יד is two Hebrew letters)
        
        Args:
            line_text: The line text to check
            
        Returns:
            Tuple of (normalized_number, suffix_canonical, suffix_display) if paragraph start detected, None otherwise
            Example: ("20", "A", "א") or ("81", "ID", "יד") or ("7", None, None)
        """
        line_text = line_text.strip()
        if not line_text:
            return None
        
        # Ignore artifacts: ranges like "69-68" or bracketed notes like "[בוטל]"
        if re.match(r'^\d+-\d+', line_text) or re.match(r'^\[בוטל\]', line_text):
            return None
        
        # PRIMARY PATTERN: Number-dot with optional Hebrew suffix (single or multi-letter)
        # Pattern: "5.", "81.", "81א.", "81יד." (dot comes AFTER number/letters)
        # Hebrew suffix can be 1-3 letters (א, ב, יד, טו, etc.)
        # Space after dot is optional (may be stripped by PDF extraction)
        # Paragraph number may be on its own line (just "1.") or on same line as content
        pattern_number_dot = re.compile(r'^(\d{1,3})([א-ת]{1,3})?\.\s*')
        match_primary = pattern_number_dot.match(line_text)
        
        if match_primary:
            number = match_primary.group(1)
            suffix_hebrew = match_primary.group(2) if match_primary.lastindex >= 2 and match_primary.group(2) else None
            
            # Check that there's content after the paragraph marker OR line is just the paragraph number
            # (content will be on next line in that case)
            rest = line_text[match_primary.end():].strip()
            # Accept if: (1) content on same line, OR (2) line is just "NUMBER." (content on next line)
            if (rest and len(rest) > 2) or (not rest and len(line_text.strip()) <= 5):
                # Convert Hebrew suffix to canonical (Latin)
                suffix_canonical = None
                if suffix_hebrew:
                    # Handle multi-letter Hebrew (e.g., "יד" -> "ID")
                    if len(suffix_hebrew) == 1:
                        suffix_canonical = hebrew_to_latin(suffix_hebrew)
                    else:
                        # Multi-letter: convert each letter
                        suffix_canonical = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                
                return (number, suffix_canonical, suffix_hebrew)
        
        # FALLBACK PATTERN 1: Dot-number with optional Hebrew suffix: ".16", ".20א", ".81יד"
        # For other PDF formats that use dot before number
        pattern_dot_number = re.compile(r'^\.(\d{1,3})([א-ת]{1,3})?\s+')
        match_dot = pattern_dot_number.match(line_text)
        if match_dot:
            number = match_dot.group(1)
            suffix_hebrew = match_dot.group(2) if match_dot.group(2) else None
            
            # Check that there's content after the paragraph marker
            rest = line_text[match_dot.end():].strip()
            if rest and len(rest) > 2:
                # Convert Hebrew suffix to canonical (Latin)
                suffix_canonical = None
                if suffix_hebrew:
                    # Handle multi-letter Hebrew (e.g., "יד" -> "ID")
                    if len(suffix_hebrew) == 1:
                        suffix_canonical = hebrew_to_latin(suffix_hebrew)
                    else:
                        # Multi-letter: convert each letter
                        suffix_canonical = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                
                return (number, suffix_canonical, suffix_hebrew)
        
        return None
    
    def _parse_main_content_from_lines(self, positioned_lines: List[Dict[str, Any]], standard_id: str) -> MainContent:
        """Parse main content from positioned lines with improved paragraph detection."""
        paragraphs: List[Paragraph] = []
        current_paragraph: Optional[Paragraph] = None
        processed_indices = set()  # Track lines that have been processed (for separate-line format)
        
        for line_idx, line in enumerate(positioned_lines):
            # Skip already processed lines
            if line_idx in processed_indices:
                continue
            line_text = line["text"]
            if not line_text.strip():
                # Empty line - continue accumulating into current paragraph
                if current_paragraph:
                    current_paragraph.content += "\n"
                continue
            
            # Skip "." lines that are part of separate-line format (number on previous line, "." on this line)
            if line_idx > 0:
                prev_line_text = positioned_lines[line_idx - 1]["text"].strip()
                if line_text.strip() == '.' and prev_line_text and re.match(r'^\d+[א-ת]?$', prev_line_text):
                    # This is a "." line following a number - skip it (content will be on next line)
                    continue
            
            # Check for number-dot on separate lines: "22" followed by "." on next line
            para_start = None
            if line_idx + 1 < len(positioned_lines):
                next_line_text = positioned_lines[line_idx + 1]["text"].strip()
                # Pattern: current line is just a number (possibly with Hebrew suffix), next line is just "."
                number_only_pattern = re.compile(r'^(\d{1,3})([א-ת]{1,3})?$')
                match_number_only = number_only_pattern.match(line_text.strip())
                if match_number_only and next_line_text == '.':
                    number = match_number_only.group(1)
                    suffix_hebrew = match_number_only.group(2) if match_number_only.lastindex >= 2 and match_number_only.group(2) else None
                    # Check if line after "." has content
                    if line_idx + 2 < len(positioned_lines):
                        content_line = positioned_lines[line_idx + 2]["text"].strip()
                        if content_line and len(content_line) > 2:
                            # Convert Hebrew suffix to canonical
                            suffix_canonical = None
                            if suffix_hebrew:
                                if len(suffix_hebrew) == 1:
                                    suffix_canonical = hebrew_to_latin(suffix_hebrew)
                                else:
                                    suffix_canonical = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                            para_start = (number, suffix_canonical, suffix_hebrew)
                            # Mark the "." line (line_idx + 1) as processed - we'll skip it
                            processed_indices.add(line_idx + 1)
            
            # If not found as separate-line format, check normal patterns
            if not para_start:
                para_start = self._detect_paragraph_start(line_text)
            
            if para_start:
                # Close previous paragraph
                if current_paragraph:
                    paragraphs.append(current_paragraph)
                
                # Extract paragraph number, canonical suffix, and display suffix
                para_number, para_suffix_canonical, para_suffix_display = para_start
                
                # Build canonical paragraph ID (e.g., "IAS_16:20A", "IAS_16:81ID")
                if para_suffix_canonical:
                    para_id = f"{standard_id}:{para_number}{para_suffix_canonical}"
                else:
                    para_id = f"{standard_id}:{para_number}"
                
                # Build display paragraph ID with Hebrew (e.g., "IAS_16:20א", "IAS_16:81יד")
                if para_suffix_display:
                    para_id_display = f"{standard_id}:{para_number}{para_suffix_display}"
                else:
                    para_id_display = None  # Same as canonical if no suffix
                
                # Extract content (everything after paragraph marker)
                # Check if this is separate-line format (number on this line, "." on next, content on line after)
                content = ""
                is_separate_line_format = (line_idx + 1 < len(positioned_lines) and 
                                          positioned_lines[line_idx + 1]["text"].strip() == '.' and
                                          para_start and line_text.strip() and 
                                          re.match(r'^\d+[א-ת]?$', line_text.strip()))
                
                if is_separate_line_format:
                    # Separate-line format: content starts on line_idx + 2
                    if line_idx + 2 < len(positioned_lines):
                        content = positioned_lines[line_idx + 2]["text"].strip()
                        # Mark the content line as processed (it's already in the paragraph)
                        processed_indices.add(line_idx + 2)
                else:
                    # Normal format: content on same line or next line
                    # Primary pattern: "5.", "81.", "81א." (number-dot format)
                    content = line_text
                    if para_suffix_display:
                        # Pattern with Hebrew suffix: "81א.", "81יד." (space after dot is optional)
                        pattern = re.compile(rf'^{re.escape(para_number)}{re.escape(para_suffix_display)}\.\s*')
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                        else:
                            # Try without suffix: "81."
                            pattern = re.compile(rf'^{re.escape(para_number)}\.\s*')
                            match = pattern.match(line_text)
                            if match:
                                content = line_text[match.end():].strip()
                            else:
                                # Fallback: try dot-prefixed pattern ".81א "
                                pattern = re.compile(rf'^\.{re.escape(para_number)}{re.escape(para_suffix_display)}\s+')
                                match = pattern.match(line_text)
                                if match:
                                    content = line_text[match.end():].strip()
                                else:
                                    # Try dot-prefixed without suffix ".81 "
                                    pattern = re.compile(rf'^\.{re.escape(para_number)}\s+')
                                    match = pattern.match(line_text)
                                    if match:
                                        content = line_text[match.end():].strip()
                    else:
                        # Pattern without suffix: "5.", "81." (space after dot is optional)
                        pattern = re.compile(rf'^{re.escape(para_number)}\.\s*')
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                        else:
                            # Fallback: try dot-prefixed pattern ".81 "
                            pattern = re.compile(rf'^\.{re.escape(para_number)}\s+')
                            match = pattern.match(line_text)
                            if match:
                                content = line_text[match.end():].strip()
                
                # Start new paragraph
                current_paragraph = Paragraph(
                    paragraph_id=para_id,
                    paragraph_id_display=para_id_display,
                    content=content,
                    clauses=[],
                    tables=[],
                    footnotes=[]
                )
            else:
                # Accumulate into current paragraph
                if current_paragraph:
                    if current_paragraph.content:
                        current_paragraph.content += " " + line_text
                    else:
                        current_paragraph.content = line_text
                else:
                    # No paragraph started yet - skip orphaned content (likely front matter/TOC)
                    # Don't create paragraph_id:0, just skip this line
                    continue
        
        # Close final paragraph
        if current_paragraph:
            paragraphs.append(current_paragraph)
        
        # Create main section with all paragraphs
        main_section = Section(
            section_title="Main Content",
            paragraphs=paragraphs,
            subsections=[]
        )
        
        return MainContent(sections=[main_section])
    
    def _split_main_and_appendices(self, positioned_lines: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        """Split positioned lines into main content and appendices.
        
        Returns:
            Tuple of (main_lines, appendix_lines_dict) where appendix_lines_dict maps 'A', 'B', 'C' to their lines
        """
        # Patterns for appendix detection
        appendix_pattern_hebrew = re.compile(r'נספח\s*([א-ת])', re.IGNORECASE)
        appendix_pattern_english = re.compile(r'Appendix\s*([A-Z])', re.IGNORECASE)
        
        main_lines = []
        appendix_lines_dict: Dict[str, List[Dict[str, Any]]] = {}
        current_appendix = None
        
        for line in positioned_lines:
            line_text = line["text"]
            
            # Check for appendix marker
            hebrew_match = appendix_pattern_hebrew.search(line_text)
            english_match = appendix_pattern_english.search(line_text)
            
            if hebrew_match:
                appendix_letter_hebrew = hebrew_match.group(1)
                # Convert Hebrew to Latin
                if appendix_letter_hebrew in HEBREW_TO_LATIN:
                    current_appendix = hebrew_to_latin(appendix_letter_hebrew)
                else:
                    current_appendix = appendix_letter_hebrew.upper()
            elif english_match:
                current_appendix = english_match.group(1).upper()
            
            # Route line to appropriate section
            if current_appendix:
                if current_appendix not in appendix_lines_dict:
                    appendix_lines_dict[current_appendix] = []
                appendix_lines_dict[current_appendix].append(line)
            else:
                main_lines.append(line)
        
        return main_lines, appendix_lines_dict
    
    def _parse_appendix(self, appendix_lines: List[Dict[str, Any]], standard_id: str, appendix_id: str) -> Appendix:
        """Parse an appendix section.
        
        Args:
            appendix_lines: Lines belonging to this appendix
            standard_id: Standard identifier (e.g., "IAS_16")
            appendix_id: Appendix identifier (e.g., "A", "B", "C")
            
        Returns:
            Appendix object with parsed content
        """
        paragraphs: List[Paragraph] = []
        current_paragraph: Optional[Paragraph] = None
        
        # Hebrew letter for this appendix (for paragraph numbering)
        hebrew_letter = None
        for heb, lat in HEBREW_TO_LATIN.items():
            if lat == appendix_id:
                hebrew_letter = heb
                break
        
        for line in appendix_lines:
            line_text = line["text"]
            if not line_text.strip():
                if current_paragraph:
                    current_paragraph.content += "\n"
                continue
            
            # Detect appendix paragraph start (e.g., "ב1", "ב2", "ג1")
            # Pattern: Hebrew letter followed by number
            if hebrew_letter:
                appendix_para_pattern = re.compile(rf'^\s*{re.escape(hebrew_letter)}(\d+)\s*')
                match = appendix_para_pattern.match(line_text)
                if match:
                    # Close previous paragraph
                    if current_paragraph:
                        paragraphs.append(current_paragraph)
                    
                    para_number = match.group(1)
                    # Build paragraph ID: IAS_16:B1 (canonical), IAS_16:ב1 (display)
                    para_id = f"{standard_id}:{appendix_id}{para_number}"
                    para_id_display = f"{standard_id}:{hebrew_letter}{para_number}"
                    
                    # Extract content
                    content = line_text[match.end():].strip()
                    
                    current_paragraph = Paragraph(
                        paragraph_id=para_id,
                        paragraph_id_display=para_id_display,
                        content=content,
                        clauses=[],
                        tables=[],
                        footnotes=[]
                    )
                    continue
            
            # Also check for regular paragraph patterns in appendices
            para_start = self._detect_paragraph_start(line_text)
            if para_start:
                if current_paragraph:
                    paragraphs.append(current_paragraph)
                
                para_number, para_suffix_canonical, para_suffix_display = para_start
                
                # Build canonical paragraph ID
                if para_suffix_canonical:
                    para_id = f"{standard_id}:{para_number}{para_suffix_canonical}"
                else:
                    para_id = f"{standard_id}:{para_number}"
                
                # Build display paragraph ID with Hebrew
                if para_suffix_display:
                    para_id_display = f"{standard_id}:{para_number}{para_suffix_display}"
                else:
                    para_id_display = None
                
                # Extract content (primary pattern: ".16", ".20א", ".81יד")
                content = line_text
                if para_suffix_display:
                    pattern = re.compile(rf'^\.{re.escape(para_number)}{re.escape(para_suffix_display)}\s+')
                    match = pattern.match(line_text)
                    if match:
                        content = line_text[match.end():].strip()
                    else:
                        pattern = re.compile(rf'^\.{re.escape(para_number)}\s+')
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                else:
                    pattern = re.compile(rf'^\.{re.escape(para_number)}\s+')
                    match = pattern.match(line_text)
                    if match:
                        content = line_text[match.end():].strip()
                
                current_paragraph = Paragraph(
                    paragraph_id=para_id,
                    paragraph_id_display=para_id_display,
                    content=content,
                    clauses=[],
                    tables=[],
                    footnotes=[]
                )
            else:
                # Accumulate into current paragraph
                if current_paragraph:
                    if current_paragraph.content:
                        current_paragraph.content += " " + line_text
                    else:
                        current_paragraph.content = line_text
        
        # Close final paragraph
        if current_paragraph:
            paragraphs.append(current_paragraph)
        
        # Create sections for appendix (for now, single section with all paragraphs)
        sections = []
        if paragraphs:
            sections.append(Section(
                section_title=f"Appendix {appendix_id}",
                paragraphs=paragraphs,
                subsections=[]
            ))
        
        return Appendix(
            appendix_id=appendix_id,
            title=None,  # Can be extracted if present
            sections=sections
        )
    
    def _parse_main_content(self, structured_text: List[Tuple[int, str, dict]], standard_id: str) -> MainContent:
        """Parse main content sections with improved Hebrew paragraph detection."""
        sections: List[Section] = []
        current_section: Optional[Section] = None
        current_subsection: Optional[Subsection] = None
        current_paragraph: Optional[Paragraph] = None
        
        # Paragraph patterns:
        # 1. Dot-number pattern: ".16 " or ".1 " (e.g., ".16 ")
        pattern_dot_number = re.compile(r'^\s*\.(\d{1,3})\s+')
        
        # 2. Number + Hebrew letter: "16א " or "20ב " (e.g., "20א ")
        # Hebrew letters: א-ת
        pattern_hebrew_suffix = re.compile(r'^\s*(\d{1,3})([א-ת])\s+')
        
        # 3. Number + Latin letter: "16A " or "20B " (already normalized)
        pattern_latin_suffix = re.compile(r'^\s*(\d{1,3})([A-Z])\s+')
        
        # 4. Plain number at start: "16 " (fallback)
        pattern_plain_number = re.compile(r'^\s*(\d{1,3})\s+')
        
        all_paragraphs: List[Paragraph] = []  # Collect all paragraphs first
        
        for page_num, text, metadata in structured_text:
            lines = text.split("\n")
            
            for line in lines:
                original_line = line
                line = line.strip()
                if not line:
                    continue
                
                # Try to detect paragraph start
                para_match = None
                para_number = None
                para_suffix = None
                para_suffix_display = None  # Original suffix for display
                
                # Try patterns in order of specificity
                match_dot = pattern_dot_number.match(line)
                if match_dot:
                    para_match = match_dot
                    para_number = match_dot.group(1)
                    para_suffix = None
                    para_suffix_display = None
                
                if not para_match:
                    match_hebrew = pattern_hebrew_suffix.match(line)
                    if match_hebrew:
                        para_match = match_hebrew
                        para_number = match_hebrew.group(1)
                        hebrew_char = match_hebrew.group(2)
                        para_suffix_display = hebrew_char
                        para_suffix = hebrew_to_latin(hebrew_char)
                
                if not para_match:
                    match_latin = pattern_latin_suffix.match(line)
                    if match_latin:
                        para_match = match_latin
                        para_number = match_latin.group(1)
                        para_suffix = match_latin.group(2)
                        para_suffix_display = para_suffix
                
                if not para_match:
                    match_plain = pattern_plain_number.match(line)
                    if match_plain:
                        # Only use plain number if it looks like a paragraph (followed by text, not just a number)
                        rest = line[match_plain.end():].strip()
                        if rest and len(rest) > 5:  # Has meaningful content after number
                            para_match = match_plain
                            para_number = match_plain.group(1)
                            para_suffix = None
                            para_suffix_display = None
                
                if para_match:
                    # Close previous paragraph if exists
                    if current_paragraph:
                        all_paragraphs.append(current_paragraph)
                    
                    # Build paragraph ID
                    if para_suffix:
                        para_id = f"{standard_id}:{para_number}{para_suffix}"
                    else:
                        para_id = f"{standard_id}:{para_number}"
                    
                    # Extract content (everything after paragraph marker)
                    content = line[para_match.end():].strip()
                    
                    # Start new paragraph
                    current_paragraph = Paragraph(
                        paragraph_id=para_id,
                        content=content,
                        clauses=[],
                        tables=[],
                        footnotes=[]
                    )
                else:
                    # Accumulate content into current paragraph
                    if current_paragraph:
                        # Add line to current paragraph content
                        if current_paragraph.content:
                            current_paragraph.content += " " + line
                        else:
                            current_paragraph.content = line
        
        # Close final paragraph
        if current_paragraph:
            all_paragraphs.append(current_paragraph)
        
        # Assign paragraphs to a section
        # For now, create a single main section if we have paragraphs
        if all_paragraphs:
            # Create a default section with all paragraphs
            main_section = Section(
                section_title="Main Content",
                paragraphs=all_paragraphs,
                subsections=[]
            )
            sections.append(main_section)
        elif not sections:
            # No paragraphs and no sections - create empty section
            sections.append(Section(
                section_title="Main Content",
                paragraphs=[],
                subsections=[]
            ))
        
        return MainContent(sections=sections)
    
    def _is_section_title(self, line: str) -> bool:
        """Heuristic to detect section titles."""
        # All caps and short
        if line.isupper() and len(line) < 100 and len(line) > 3:
            return True
        # Starts with number and is short
        if re.match(r"^\d+\.?\s+[A-Z]", line) and len(line) < 100:
            return True
        return False
    
    def _is_subsection_title(self, line: str) -> bool:
        """Heuristic to detect subsection titles."""
        # Pattern like "A. Title" or "(a) Title"
        if re.match(r"^[A-Za-z]\.|^\([a-z]\)|^[A-Z]\s+[A-Z]", line[:20]):
            return True
        return False
    
    def _extract_definitions(self, structured_text: List[Tuple[int, str, dict]], standard_id: str, document: StandardDocument) -> List[Definition]:
        """Extract definitions ONLY from "הגדרות" section (paragraph 6) or Appendix A if present.
        
        Do not run heuristics on the whole document.
        """
        definitions: List[Definition] = []
        
        # First check if Appendix A exists and contains definitions
        if document.appendix_A:
            # Extract from Appendix A sections
            for section in document.appendix_A.sections:
                for para in section.paragraphs:
                    # Look for definition patterns in paragraph content
                    # Pattern: Hebrew term: definition or English term means definition
                    definition_patterns = [
                        r"([\u0590-\u05FF\w\s]{3,50})\s*[:–—]\s*(.+?)(?=\n|$)",  # Hebrew term: definition
                        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*means?\s+(.+?)(?=\n|$)",  # English term means definition
                    ]
                    for pattern in definition_patterns:
                        matches = re.finditer(pattern, para.content, re.MULTILINE | re.IGNORECASE)
                        for match in matches:
                            term = match.group(1).strip()
                            definition = match.group(2).strip()
                            
                            if len(term) > 2 and len(definition) > 10:
                                definitions.append(Definition(
                                    term=term,
                                    definition=definition,
                                    referenced_from=[para.paragraph_id]
                                ))
            # If found in Appendix A, return early
            if definitions:
                return definitions
        
        # Otherwise, look for "הגדרות" section (paragraph 6)
        # Find paragraph 6 in main content
        for section in document.main.sections:
            for para in section.paragraphs:
                # Check if this is paragraph 6 (IAS_16:6)
                if para.paragraph_id == f"{standard_id}:6":
                    # Look for definition patterns in paragraph 6 content
                    definition_patterns = [
                        r"([\u0590-\u05FF\w\s]{3,50})\s*[:–—]\s*(.+?)(?=\n|$)",  # Hebrew term: definition
                        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*means?\s+(.+?)(?=\n|$)",  # English term means definition
                    ]
                    for pattern in definition_patterns:
                        matches = re.finditer(pattern, para.content, re.MULTILINE | re.IGNORECASE)
                        for match in matches:
                            term = match.group(1).strip()
                            definition = match.group(2).strip()
                            
                            if len(term) > 2 and len(definition) > 10:
                                definitions.append(Definition(
                                    term=term,
                                    definition=definition,
                                    referenced_from=[para.paragraph_id]
                                ))
                    break
        
        return definitions
    
    def _extract_exclusions(self, structured_text: List[Tuple[int, str, dict]]) -> Exclusions:
        """Extract untranslated sections."""
        exclusions = Exclusions(untranslated_sections=[])
        
        exclusion_markers = [
            "לא תורגם",
            "not translated",
            "untranslated",
            "under translation"
        ]
        
        for page_num, text, metadata in structured_text:
            for marker in exclusion_markers:
                if marker.lower() in text.lower():
                    # Try to identify the section
                    lines = text.split("\n")
                    for i, line in enumerate(lines):
                        if marker.lower() in line.lower():
                            # Look for section title nearby
                            section_title = None
                            for j in range(max(0, i-3), min(len(lines), i+3)):
                                if self._is_section_title(lines[j]):
                                    section_title = lines[j]
                                    break
                            
                            exclusions.untranslated_sections.append(Exclusion(
                                page=page_num,
                                section=section_title or f"Unknown section on page {page_num}",
                                reason=f"Contains exclusion marker: {marker}"
                            ))
                            break
        
        return exclusions
    
    def _calculate_confidence(self, document: StandardDocument, baseline_text: str) -> float:
        """Calculate confidence score for parsed document."""
        # Basic heuristic: more structure = higher confidence
        total_paragraphs = sum(
            len(s.paragraphs) + sum(len(sub.paragraphs) for sub in s.subsections)
            for s in document.main.sections
        )
        
        # Normalize confidence based on document size
        if total_paragraphs == 0:
            return 0.1
        
        # Higher confidence if we found reasonable structure
        if total_paragraphs > 5:
            return min(0.9, 0.5 + (total_paragraphs / 100.0))
        
        return 0.3 + (total_paragraphs / 20.0)


class Extractor:
    """Orchestrates multiple parsing strategies."""
    
    def __init__(self):
        """Initialize extractor with available strategies."""
        self.strategies: List[ParsingStrategy] = [
            SimpleStrategy(),  # Start with simple strategy
            # Can add more strategies here
        ]
    
    def extract(self, extractor: PDFTextExtractor, standard_id: str) -> Tuple[StandardDocument, float]:
        """Try parsing strategies and return best result.
        
        Args:
            extractor: PDFTextExtractor instance
            standard_id: Standard identifier
            
        Returns:
            Tuple of (best StandardDocument, highest_confidence_score)
        """
        best_document = None
        best_confidence = 0.0
        
        for strategy in self.strategies:
            try:
                document, confidence = strategy.parse(extractor, standard_id)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_document = document
            except Exception as e:
                # Strategy failed, try next one
                continue
        
        if best_document is None:
            # Return minimal document if all strategies fail
            best_document = StandardDocument(
                standard_id=standard_id,
                standard_title=StandardTitle(),
                main=MainContent(sections=[]),
                definitions=[],
                exclusions=Exclusions(untranslated_sections=[])
            )
            best_confidence = 0.0
        
        return best_document, best_confidence

