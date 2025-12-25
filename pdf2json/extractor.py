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
        
        # Extract definitions (basic pattern matching)
        structured_text = extractor.extract_text_with_structure()
        definitions = self._extract_definitions(structured_text, standard_id)
        
        # Extract exclusions (look for untranslated markers)
        exclusions = self._extract_exclusions(structured_text)
        
        document = StandardDocument(
            standard_id=standard_id,
            standard_title=standard_title,
            main=main_content,
            appendix_A=appendix_A,
            appendix_B=appendix_B,
            appendix_C=appendix_C,
            definitions=definitions,
            exclusions=exclusions
        )
        
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
            match_end = hebrew_match.end()
            remaining_text = page1_text[match_end:]
            
            # Look for next Hebrew line (subject)
            hebrew_subject_pattern = re.compile(r'([א-ת\s]{3,50})', re.MULTILINE)
            subject_matches = hebrew_subject_pattern.findall(remaining_text[:500])
            
            subject = None
            for match in subject_matches:
                text = match.strip()
                # Skip if it's just the standard number or very short
                if len(text) > 3 and text != standard_number and not text.isdigit():
                    subject = text
                    break
            
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
            if match_line_idx is not None:
                # Look at next few lines for the subject
                for idx in range(match_line_idx + 1, min(match_line_idx + 5, len(page1_lines))):
                    line_text = page1_lines[idx]["text"].strip()
                    # Check if line contains title case words (subject line)
                    # Pattern: title case words separated by spaces/commas
                    subject_pattern = re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)$')
                    if subject_pattern.match(line_text):
                        # Skip if it's just "International Accounting Standard" or similar
                        if (len(line_text) > 10 and 
                            "International" not in line_text and 
                            "Accounting" not in line_text and
                            "Standard" not in line_text):
                            subject = line_text
                            break
                    # Also try a more flexible pattern for multi-line subjects
                    elif re.match(r'^[A-Z][a-z]+', line_text) and len(line_text) > 5:
                        # Check if it looks like a subject (not a header word)
                        skip_words = ["International", "Accounting", "Standard", "Financial", "Reporting"]
                        if not any(word in line_text for word in skip_words):
                            subject = line_text
                            break
            
            # Fallback: search in remaining text if not found in lines
            if not subject:
                match_end = english_match.end()
                remaining_text = page1_text[match_end:]
                # Look for next English line (subject) - more flexible pattern
                english_subject_pattern = re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,6}(?:\s*,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)*)', re.MULTILINE)
                subject_matches = english_subject_pattern.findall(remaining_text[:800])
                
                for match in subject_matches:
                    text = match.strip()
                    # Skip if it's too short or looks like a header
                    if (len(text) > 8 and 
                        text not in ["International", "Accounting", "Standard"] and
                        "International" not in text and
                        "Accounting" not in text):
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
        
        # Pattern for paragraph start: r'^\s*\.?\d+[א-ת]?\s' or r'^\s*\d+[א-ת]?\.'
        # Also handle patterns like "20א", "81ה", etc.
        # Specifically look for paragraph 1: ".1", "1.", "1 "
        para_pattern1 = re.compile(r'^\s*\.?\d+[א-ת]?\s+')
        para_pattern2 = re.compile(r'^\s*\d+[א-ת]?\.\s*')
        para_pattern3 = re.compile(r'^\s*\.\d+[א-ת]?\s+')  # ".20א "
        para_pattern_dot_one = re.compile(r'^\s*\.1\s+')  # ".1 "
        para_pattern_one_dot = re.compile(r'^\s*1\.\s+')  # "1. "
        para_pattern_one = re.compile(r'^\s*1\s+')  # "1 " (more conservative)
        
        toc_pages = set()
        main_start_index = 0
        found_heading = False
        
        # Find TOC pages - mark all pages that contain TOC
        for i, line in enumerate(positioned_lines):
            if toc_pattern.search(line["text"]):
                toc_pages.add(line["page"])
                # Also mark subsequent pages if TOC spans multiple pages
                # (heuristic: if TOC found, mark next 2 pages as potentially TOC)
                for p in range(line["page"], min(line["page"] + 3, 100)):
                    toc_pages.add(p)
        
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
                # Look for paragraph 1 specifically first
                if (para_pattern_dot_one.match(line["text"]) or 
                    para_pattern_one_dot.match(line["text"]) or
                    (para_pattern_one.match(line["text"]) and len(line["text"].strip()) > 2)):
                    main_start_index = i
                    break
                # Also accept other paragraph patterns if heading was found
                elif (para_pattern1.match(line["text"]) or 
                      para_pattern2.match(line["text"]) or 
                      para_pattern3.match(line["text"])):
                    main_start_index = i
                    break
            else:
                # If no heading found yet, look for paragraph 1 as start indicator
                if (para_pattern_dot_one.match(line["text"]) or 
                    para_pattern_one_dot.match(line["text"])):
                    main_start_index = i
                    break
                # Fallback: any paragraph pattern if no heading
                elif (para_pattern1.match(line["text"]) or 
                      para_pattern2.match(line["text"]) or 
                      para_pattern3.match(line["text"])):
                    # Only use if it's a low number (likely paragraph 1-10)
                    match = re.match(r'^\s*\.?(\d+)', line["text"])
                    if match:
                        para_num = int(match.group(1))
                        if para_num <= 10:  # Likely early paragraph
                            main_start_index = i
                            break
        
        return main_start_index
    
    def _detect_paragraph_start(self, line_text: str) -> Optional[Tuple[str, str]]:
        """Detect if a line starts with a paragraph number token.
        
        Supports formats: "7.", "20 .א", "29א.", "68א.", "81א.", "20A", "20א", etc.
        
        Args:
            line_text: The line text to check
            
        Returns:
            Tuple of (normalized_number, suffix) if paragraph start detected, None otherwise
            Example: ("20", "א") or ("7", None)
        """
        line_text = line_text.strip()
        if not line_text:
            return None
        
        # Pattern 1: Dot-number pattern (highest priority for ".1", ".2", etc.): ".1 ", ".16 "
        pattern_dot_number = re.compile(r'^\.(\d{1,3})\s+')
        match_dot = pattern_dot_number.match(line_text)
        if match_dot:
            number = match_dot.group(1)
            rest = line_text[match_dot.end():].strip()
            if rest and len(rest) > 2:
                return (number, None)
        
        # Pattern 1b: Number followed by dot and optional Hebrew/Latin letter: "7.", "20א.", "29א."
        # Also handles "20 .א" (space before letter)
        pattern1 = re.compile(r'^(\d{1,3})\s*\.?\s*([א-תA-Z])?\s*\.?\s*')
        match1 = pattern1.match(line_text)
        if match1:
            number = match1.group(1)
            suffix = match1.group(2) if match1.group(2) else None
            # Check that there's content after the paragraph marker
            rest = line_text[match1.end():].strip()
            if rest and len(rest) > 2:  # Has meaningful content
                return (number, suffix)
        
        # Pattern 2: Number followed by space and Hebrew/Latin letter: "20א ", "20A "
        pattern2 = re.compile(r'^(\d{1,3})([א-תA-Z])\s+')
        match2 = pattern2.match(line_text)
        if match2:
            number = match2.group(1)
            suffix = match2.group(2)
            rest = line_text[match2.end():].strip()
            if rest and len(rest) > 2:
                return (number, suffix)
        
        # Pattern 3: Number followed by dot and space: "7. ", "20. "
        pattern3 = re.compile(r'^(\d{1,3})\s*\.\s+')
        match3 = pattern3.match(line_text)
        if match3:
            number = match3.group(1)
            rest = line_text[match3.end():].strip()
            if rest and len(rest) > 2:
                return (number, None)
        
        # Pattern 4: Plain number at start (more conservative): "7 ", "20 "
        pattern4 = re.compile(r'^(\d{1,3})\s+')
        match4 = pattern4.match(line_text)
        if match4:
            number = match4.group(1)
            rest = line_text[match4.end():].strip()
            # Only accept if followed by substantial content (not just a number)
            if rest and len(rest) > 5 and not rest[0].isdigit():
                return (number, None)
        
        return None
    
    def _parse_main_content_from_lines(self, positioned_lines: List[Dict[str, Any]], standard_id: str) -> MainContent:
        """Parse main content from positioned lines with improved paragraph detection."""
        paragraphs: List[Paragraph] = []
        current_paragraph: Optional[Paragraph] = None
        
        for line in positioned_lines:
            line_text = line["text"]
            if not line_text.strip():
                # Empty line - continue accumulating into current paragraph
                if current_paragraph:
                    current_paragraph.content += "\n"
                continue
            
            # Check if this line starts a new paragraph
            para_start = self._detect_paragraph_start(line_text)
            
            if para_start:
                # Close previous paragraph
                if current_paragraph:
                    paragraphs.append(current_paragraph)
                
                # Extract paragraph number and suffix
                para_number, para_suffix_raw = para_start
                
                # Normalize suffix: convert Hebrew to Latin, remove spaces
                para_suffix = None
                if para_suffix_raw:
                    if para_suffix_raw in HEBREW_TO_LATIN:
                        para_suffix = hebrew_to_latin(para_suffix_raw)
                    else:
                        para_suffix = para_suffix_raw.upper()
                
                # Build paragraph ID
                if para_suffix:
                    para_id = f"{standard_id}:{para_number}{para_suffix}"
                else:
                    para_id = f"{standard_id}:{para_number}"
                
                # Extract content (everything after paragraph marker)
                # Use the same detection logic to find where content starts
                content = line_text
                
                # Try to match the patterns again to extract content
                if para_suffix_raw:
                    # Pattern with suffix: "20א.", "20 .א", "20א "
                    patterns_with_suffix = [
                        re.compile(rf'^{re.escape(para_number)}\s*\.?\s*{re.escape(para_suffix_raw)}\s*\.?\s*'),
                        re.compile(rf'^{re.escape(para_number)}\s*\.\s*{re.escape(para_suffix_raw)}\s*'),
                        re.compile(rf'^{re.escape(para_number)}{re.escape(para_suffix_raw)}\s+'),
                    ]
                    for pattern in patterns_with_suffix:
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                            break
                else:
                    # Pattern without suffix: "7.", "7. ", "7 "
                    patterns_no_suffix = [
                        re.compile(rf'^{re.escape(para_number)}\s*\.\s+'),
                        re.compile(rf'^{re.escape(para_number)}\s*\.'),
                        re.compile(rf'^{re.escape(para_number)}\s+'),
                    ]
                    for pattern in patterns_no_suffix:
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                            break
                
                # Start new paragraph
                current_paragraph = Paragraph(
                    paragraph_id=para_id,
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
                    
                    # Extract content
                    content = line_text[match.end():].strip()
                    
                    current_paragraph = Paragraph(
                        paragraph_id=para_id,
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
                
                para_number, para_suffix_raw = para_start
                para_suffix = None
                if para_suffix_raw:
                    if para_suffix_raw in HEBREW_TO_LATIN:
                        para_suffix = hebrew_to_latin(para_suffix_raw)
                    else:
                        para_suffix = para_suffix_raw.upper()
                
                if para_suffix:
                    para_id = f"{standard_id}:{para_number}{para_suffix}"
                else:
                    para_id = f"{standard_id}:{para_number}"
                
                # Extract content
                content = line_text
                if para_suffix_raw:
                    patterns_with_suffix = [
                        re.compile(rf'^{re.escape(para_number)}\s*\.?\s*{re.escape(para_suffix_raw)}\s*\.?\s*'),
                        re.compile(rf'^{re.escape(para_number)}\s*\.\s*{re.escape(para_suffix_raw)}\s*'),
                        re.compile(rf'^{re.escape(para_number)}{re.escape(para_suffix_raw)}\s+'),
                    ]
                    for pattern in patterns_with_suffix:
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                            break
                else:
                    patterns_no_suffix = [
                        re.compile(rf'^{re.escape(para_number)}\s*\.\s+'),
                        re.compile(rf'^{re.escape(para_number)}\s*\.'),
                        re.compile(rf'^{re.escape(para_number)}\s+'),
                    ]
                    for pattern in patterns_no_suffix:
                        match = pattern.match(line_text)
                        if match:
                            content = line_text[match.end():].strip()
                            break
                
                current_paragraph = Paragraph(
                    paragraph_id=para_id,
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
    
    def _extract_definitions(self, structured_text: List[Tuple[int, str, dict]], standard_id: str) -> List[Definition]:
        """Extract definitions using pattern matching."""
        definitions: List[Definition] = []
        
        # Common definition patterns
        definition_patterns = [
            r"([\u0590-\u05FF\w\s]+)\s*[:–—]\s*(.+?)(?=\n\n|\n[A-Z]|$)",  # Hebrew term: definition
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*means?\s+(.+?)(?=\n|$)",  # English term means definition
        ]
        
        for page_num, text, metadata in structured_text:
            for pattern in definition_patterns:
                matches = re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE)
                for match in matches:
                    term = match.group(1).strip()
                    definition = match.group(2).strip()
                    
                    if len(term) > 2 and len(definition) > 10:
                        definitions.append(Definition(
                            term=term,
                            definition=definition,
                            referenced_from=[]
                        ))
        
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

