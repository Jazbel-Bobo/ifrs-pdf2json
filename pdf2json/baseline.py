"""Baseline extraction for debug pipeline."""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from pdf2json.parser import PDFTextExtractor


class BaselineExtractor:
    """Extracts baseline information from PDF for debugging."""
    
    def __init__(self, pdf_extractor: PDFTextExtractor):
        """Initialize baseline extractor.
        
        Args:
            pdf_extractor: PDFTextExtractor instance
        """
        self.pdf_extractor = pdf_extractor
    
    def extract_baseline(self, standard_id: str) -> Dict[str, Any]:
        """Extract baseline information from PDF using page.get_text("text").
        
        Args:
            standard_id: Standard ID (e.g., "IAS_16")
            
        Returns:
            Dictionary with baseline information including validation status
        """
        if not self.pdf_extractor.doc:
            raise ValueError("PDF document not open. Use context manager.")
        
        # Get per-page text using page.get_text("text")
        page_texts: Dict[int, List[str]] = {}
        # #region agent log
        import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "A", "location": "baseline.py:31", "message": "Starting page text extraction", "data": {"total_pages": len(self.pdf_extractor.doc)}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
        # #endregion
        for page_num in range(len(self.pdf_extractor.doc)):
            page = self.pdf_extractor.doc[page_num]
            page_text = page.get_text("text")
            # Split into lines and filter empty
            lines = [line.strip() for line in page_text.split("\n") if line.strip()]
            page_texts[page_num + 1] = lines  # 1-indexed page numbers
            # #region agent log
            import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "D", "location": f"baseline.py:38", "message": "Page text extracted", "data": {"page": page_num + 1, "text_length": len(page_text), "line_count": len(lines), "sample_lines": lines[:5] if lines else []}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
            # #endregion
        
        # Extract TOC pages
        toc_pages = self._extract_toc_pages(page_texts)
        # #region agent log
        import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "C", "location": "baseline.py:42", "message": "TOC pages detected", "data": {"toc_pages": sorted(list(toc_pages)), "total_pages": len(page_texts)}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
        # #endregion
        
        # Extract title candidates from page 1
        title_candidates = self._extract_title_candidates(page_texts.get(1, []))
        
        # Extract paragraph candidates from non-TOC pages
        paragraph_candidates = self._extract_paragraph_candidates(page_texts, toc_pages, standard_id)
        
        baseline = {
            "toc_pages": sorted(list(toc_pages)),
            "title": title_candidates,
            "paragraph_candidates": paragraph_candidates
        }
        
        # Validate baseline
        baseline_valid, validation_reasons = self._validate_baseline(baseline, standard_id)
        baseline["baseline_valid"] = baseline_valid
        baseline["baseline_validation_reasons"] = validation_reasons
        
        return baseline
    
    def _extract_toc_pages(self, page_texts: Dict[int, List[str]]) -> Set[int]:
        """Extract page numbers containing TOC.
        
        Args:
            page_texts: Dictionary mapping page numbers to lists of lines
            
        Returns:
            Set of page numbers containing TOC
        """
        toc_pattern = re.compile(r'תוכן\s+עניינים', re.IGNORECASE)
        toc_pages = set()
        
        for page_num, lines in page_texts.items():
            page_text = "\n".join(lines)
            if toc_pattern.search(page_text):
                toc_pages.add(page_num)
        
        return toc_pages
    
    def _extract_title_candidates(self, page1_lines: List[str]) -> Dict[str, Any]:
        """Extract title candidates from page 1.
        
        Args:
            page1_lines: List of text lines from page 1
            
        Returns:
            Dictionary with hebrew and english title candidates
        """
        if not page1_lines:
            return {"hebrew": None, "english": None}
        
        page1_text = "\n".join(page1_lines)
        
        # Extract Hebrew title
        hebrew_pattern = re.compile(r'תקן\s+חשבונאות\s+בינלאומי\s+(\d+)', re.IGNORECASE)
        hebrew_title = None
        standard_number = None
        
        hebrew_match = hebrew_pattern.search(page1_text)
        if hebrew_match:
            standard_number = hebrew_match.group(1)
            # Find next meaningful Hebrew line (subject)
            match_line_idx = None
            for idx, line in enumerate(page1_lines):
                if hebrew_pattern.search(line):
                    match_line_idx = idx
                    break
            
            subject = None
            if match_line_idx is not None:
                for idx in range(match_line_idx + 1, min(match_line_idx + 5, len(page1_lines))):
                    line_text = page1_lines[idx].strip()
                    if re.match(r'^[א-ת\s]{4,30}$', line_text) and len(line_text.split()) <= 4:
                        if len(line_text) > 3 and not line_text.isdigit():
                            subject = line_text
                            break
            
            if subject:
                hebrew_title = f"תקן חשבונאות בינלאומי {standard_number} {subject}"
            else:
                hebrew_title = f"תקן חשבונאות בינלאומי {standard_number}"
        
        # Extract English title
        english_pattern = re.compile(r'International\s+Accounting\s+Standard\s+(\d+)', re.IGNORECASE)
        english_title = None
        
        english_match = english_pattern.search(page1_text)
        if english_match:
            if not standard_number:
                standard_number = english_match.group(1)
            
            # Find the line with "International Accounting Standard"
            match_line_idx = None
            for idx, line in enumerate(page1_lines):
                if english_pattern.search(line):
                    match_line_idx = idx
                    break
            
            if match_line_idx is not None:
                # Collect subsequent title lines (title-case phrases)
                subject_parts = []
                # Look ahead for title lines (typically 1-3 lines after the standard number line)
                for idx in range(match_line_idx + 1, min(match_line_idx + 6, len(page1_lines))):
                    line_text = page1_lines[idx].strip()
                    if not line_text:
                        continue
                    
                    # Match title-case phrases (e.g., "Property, Plant and Equipment")
                    # Can be comma-separated or multi-word
                    if re.match(r'^[A-Z][a-z]+(?:\s+[a-z]+)*(?:\s*,\s*[A-Z][a-z]+(?:\s+[a-z]+)*)*$', line_text):
                        skip_words = ["International", "Accounting", "Standard", "Financial", "Reporting"]
                        if not any(word in line_text for word in skip_words):
                            subject_parts.append(line_text)
                            # Stop if we hit something that looks like end of title (e.g., numbers, dates, or Hebrew)
                            if re.search(r'\d{4}|\d{1,2}/\d{1,2}', line_text) or re.search(r'[א-ת]', line_text):
                                break
                    # Also accept single capitalized words that aren't skip words
                    elif re.match(r'^[A-Z][a-z]{3,}$', line_text):
                        skip_words = ["International", "Accounting", "Standard", "Financial", "Reporting", "The"]
                        if line_text not in skip_words and not re.search(r'[א-ת]', line_text):
                            subject_parts.append(line_text)
                
                if subject_parts:
                    # Join parts, handling commas properly
                    english_title = " ".join(subject_parts)
                    english_title = re.sub(r'\s*,\s*', ', ', english_title)
            
            if not english_title and standard_number:
                english_title = f"International Accounting Standard {standard_number}"
        
        return {
            "hebrew": hebrew_title,
            "english": english_title
        }
    
    def _extract_paragraph_candidates(self, page_texts: Dict[int, List[str]], toc_pages: Set[int], standard_id: str) -> List[Dict[str, Any]]:
        """Extract paragraph candidates from non-TOC pages.
        
        Args:
            page_texts: Dictionary mapping page numbers to lists of lines
            toc_pages: Set of TOC page numbers
            standard_id: Standard ID (e.g., "IAS_16")
            
        Returns:
            List of paragraph candidate dictionaries
        """
        candidates = []
        
        # Primary pattern: Number-dot with optional Hebrew suffix: "5.", "81.", "81א." (dot comes AFTER number/letters)
        # This is the correct format per user specification: NUMBER. or NUMBERLETTER.
        # Handle both "17." and "17 ." formats (space before/after dot is optional)
        pattern_number_dot_hebrew = re.compile(r'^(\d{1,3})([א-ת]{1,3})?\s*\.\s*')
        
        # Fallback pattern 1: Dot-number pattern: ".1 " or ".16 " (for other PDF formats)
        pattern_dot_number = re.compile(r'^\.(\d{1,3})([א-ת]{1,3})?\s+')
        
        # Fallback pattern 2: Plain number at start: "1 " or "16 " (for formats without dots)
        pattern_plain_number = re.compile(r'^(\d{1,3})([א-ת]{1,3})?\s+')
        
        # Import hebrew_to_latin mapping
        from pdf2json.extractor import hebrew_to_latin
        
        for page_num, lines in page_texts.items():
            # Skip TOC pages
            if page_num in toc_pages:
                # #region agent log
                import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "C", "location": f"baseline.py:201", "message": "Skipping TOC page", "data": {"page": page_num}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
                # #endregion
                continue
            
            # #region agent log
            import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "E", "location": f"baseline.py:205", "message": "Processing non-TOC page", "data": {"page": page_num, "line_count": len(lines), "sample_lines": lines[:10] if lines else []}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
            # #endregion
            
            # Process each line on this page
            for line_idx, line_text in enumerate(lines):
                line_text = line_text.strip()
                if not line_text:
                    continue
                
                matched = False
                number = None
                suffix = None
                suffix_display = None
                regex_name = None
                
                # Check for number-dot on separate lines: "22" followed by "." on next line
                # This handles cases where paragraph number and dot are split across lines
                if line_idx + 1 < len(lines):
                    next_line = lines[line_idx + 1].strip()
                    # Pattern: current line is just a number (possibly with Hebrew suffix), next line is just "."
                    number_only_pattern = re.compile(r'^(\d{1,3})([א-ת]{1,3})?$')
                    match_number_only = number_only_pattern.match(line_text)
                    if match_number_only and next_line == '.':
                        number = match_number_only.group(1)
                        suffix_hebrew = match_number_only.group(2) if match_number_only.lastindex >= 2 and match_number_only.group(2) else None
                        # Check if line after "." has content
                        content_line_idx = line_idx + 2
                        has_content = False
                        if content_line_idx < len(lines):
                            content_line = lines[content_line_idx].strip()
                            has_content = bool(content_line and len(content_line) > 2)
                        
                        if has_content:
                            if suffix_hebrew:
                                if len(suffix_hebrew) == 1:
                                    suffix = hebrew_to_latin(suffix_hebrew)
                                else:
                                    suffix = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                                suffix_display = suffix_hebrew
                            else:
                                suffix = None
                                suffix_display = None
                            regex_name = "number-dot-separate"
                            matched = True
                
                # PRIMARY PATTERN: Number-dot with optional Hebrew suffix: "5.", "81.", "81א.", "17 ."
                # Format: NUMBER. or NUMBERLETTER. (dot comes AFTER number/letters)
                # Handle both "17." and "17 ." formats (space before dot is optional)
                # Paragraph number may be on its own line (followed by content on next line) or on same line as content
                if not matched:
                    match_primary = pattern_number_dot_hebrew.match(line_text)
                if match_primary:
                    # Check if there's content after the paragraph marker on the same line
                    rest = line_text[match_primary.end():].strip()
                    # Also check if next line has content (paragraph number on its own line)
                    next_line_has_content = False
                    if line_idx + 1 < len(lines):
                        next_line = lines[line_idx + 1].strip()
                        next_line_has_content = bool(next_line and len(next_line) > 2)
                    
                    # Accept if content on same line OR next line has content (even if short)
                    # Be lenient - accept if next line exists and is not empty
                    if (rest and len(rest) > 2) or (line_idx + 1 < len(lines) and lines[line_idx + 1].strip()):
                        number = match_primary.group(1)
                        suffix_hebrew = match_primary.group(2) if match_primary.lastindex >= 2 and match_primary.group(2) else None
                        if suffix_hebrew:
                            # Handle multi-letter Hebrew (e.g., "יד" -> "ID")
                            if len(suffix_hebrew) == 1:
                                suffix = hebrew_to_latin(suffix_hebrew)
                            else:
                                suffix = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                            suffix_display = suffix_hebrew
                        else:
                            suffix = None
                            suffix_display = None
                        regex_name = "number-dot"
                        matched = True
                
                # FALLBACK PATTERN 1: Dot-number pattern: ".1 ", ".16 ", ".81א " (for other PDF formats)
                if not matched:
                    match_dot = pattern_dot_number.match(line_text)
                    if match_dot:
                        rest = line_text[match_dot.end():].strip()
                        if rest and len(rest) > 2:
                            number = match_dot.group(1)
                            suffix_hebrew = match_dot.group(2) if match_dot.lastindex >= 2 and match_dot.group(2) else None
                            if suffix_hebrew:
                                if len(suffix_hebrew) == 1:
                                    suffix = hebrew_to_latin(suffix_hebrew)
                                else:
                                    suffix = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                                suffix_display = suffix_hebrew
                            else:
                                suffix = None
                                suffix_display = None
                            regex_name = "dot-number"
                            matched = True
                
                # FALLBACK PATTERN 2: Plain number: "1 ", "16 ", "81א " (for formats without dots)
                if not matched:
                    match_plain = pattern_plain_number.match(line_text)
                    if match_plain:
                        rest = line_text[match_plain.end():].strip()
                        # Only use if has meaningful content
                        if rest and len(rest) > 5:
                            number = match_plain.group(1)
                            suffix_hebrew = match_plain.group(2) if match_plain.lastindex >= 2 and match_plain.group(2) else None
                            if suffix_hebrew:
                                if len(suffix_hebrew) == 1:
                                    suffix = hebrew_to_latin(suffix_hebrew)
                                else:
                                    suffix = "".join(hebrew_to_latin(c) for c in suffix_hebrew)
                                suffix_display = suffix_hebrew
                            else:
                                suffix = None
                                suffix_display = None
                            regex_name = "plain-number"
                            matched = True
                
                if matched and number:
                    # Build token_raw (display version)
                    token_raw = number
                    if suffix_display:
                        token_raw += suffix_display
                    
                    # Build canonical token
                    if suffix:
                        token = f"{standard_id}:{number}{suffix}"
                    else:
                        token = f"{standard_id}:{number}"
                    
                    # Build snippet: matched_line + next_line if available
                    matched_line = line_text
                    snippet = matched_line
                    
                    # Always try to add next line if available (paragraph number may be on its own line)
                    if line_idx + 1 < len(lines):
                        next_line = lines[line_idx + 1].strip()
                        if next_line:
                            # If matched_line is just the paragraph number (e.g., "1."), use next line as snippet
                            if len(matched_line.strip()) <= 5:  # Just "1." or "81א."
                                snippet = next_line[:80]
                            else:
                                snippet = matched_line + " " + next_line[:80]
                    
                    # Ensure snippet is not empty (use matched_line if needed)
                    if not snippet.strip():
                        snippet = matched_line[:80] if matched_line else ""
                    
                    # #region agent log
                    import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run2", "hypothesisId": "ALL", "location": f"baseline.py:285", "message": "Candidate added", "data": {"page": page_num, "token": token, "token_raw": token_raw, "regex_name": regex_name}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
                    # #endregion
                    
                    candidates.append({
                        "page": page_num,
                        "token": token,
                        "token_raw": token_raw,
                        "matched_line": matched_line,
                        "snippet": snippet,
                        "regex_name": regex_name
                    })
        
        # #region agent log
        import json; log_file = open('.cursor/debug.log', 'a', encoding='utf-8'); log_file.write(json.dumps({"sessionId": "debug-baseline", "runId": "run1", "hypothesisId": "ALL", "location": "baseline.py:275", "message": "Paragraph candidates extraction complete", "data": {"total_candidates": len(candidates), "candidates_by_page": {p: sum(1 for c in candidates if c["page"] == p) for p in set(c["page"] for c in candidates)}}, "timestamp": __import__("time").time() * 1000}) + "\n"); log_file.close()
        # #endregion
        
        return candidates
    
    def _validate_baseline(self, baseline: Dict[str, Any], standard_id: str) -> Tuple[bool, List[str]]:
        """Validate baseline quality.
        
        Args:
            baseline: Baseline dictionary
            standard_id: Standard ID (e.g., "IAS_16")
            
        Returns:
            Tuple of (baseline_valid: bool, reasons: List[str])
        """
        reasons = []
        candidates = baseline.get("paragraph_candidates", [])
        
        # Check 1: Minimum paragraph count
        min_required = 60 if standard_id == "IAS_16" else 30
        if len(candidates) < min_required:
            reasons.append(f"Paragraph count {len(candidates)} < {min_required}")
        
        # Check 2: >= 90% of candidates must have non-empty snippet
        if candidates:
            non_empty_snippets = sum(1 for c in candidates if c.get("snippet", "").strip())
            snippet_ratio = non_empty_snippets / len(candidates)
            if snippet_ratio < 0.90:
                reasons.append(f"Only {snippet_ratio:.1%} of candidates have non-empty snippets (required >= 90%)")
        
        # Check 3: For IAS_16, page 4 must include tokens ".1" and ".2" with non-empty snippets
        if standard_id == "IAS_16":
            page4_candidates = [c for c in candidates if c.get("page") == 4]
            page4_tokens = {c.get("token_raw", "") for c in page4_candidates}
            has_1 = any("1" in token and token.strip() in ("1", ".1") for token in page4_tokens)
            has_2 = any("2" in token and token.strip() in ("2", ".2") for token in page4_tokens)
            
            # More flexible check: look for tokens that map to "1" and "2" (e.g., IAS_16:1, IAS_16:2)
            page4_tokens_canonical = {c.get("token", "") for c in page4_candidates}
            has_1_canonical = f"{standard_id}:1" in page4_tokens_canonical
            has_2_canonical = f"{standard_id}:2" in page4_tokens_canonical
            
            if not (has_1_canonical or has_1):
                reasons.append(f"Page 4 missing token '.1' or '{standard_id}:1'")
            if not (has_2_canonical or has_2):
                reasons.append(f"Page 4 missing token '.2' or '{standard_id}:2'")
            
            # Also check snippets are non-empty for these tokens
            if has_1_canonical or has_1:
                token_1_candidates = [c for c in page4_candidates if "1" in c.get("token_raw", "") or c.get("token", "").endswith(":1")]
                if token_1_candidates and not token_1_candidates[0].get("snippet", "").strip():
                    reasons.append("Page 4 token '.1' has empty snippet")
            if has_2_canonical or has_2:
                token_2_candidates = [c for c in page4_candidates if "2" in c.get("token_raw", "") or c.get("token", "").endswith(":2")]
                if token_2_candidates and not token_2_candidates[0].get("snippet", "").strip():
                    reasons.append("Page 4 token '.2' has empty snippet")
        
        # Check 4: English title must have at least 2 words (if present)
        english_title = baseline.get("title", {}).get("english")
        if english_title:
            words = english_title.split()
            if len(words) < 2:
                reasons.append(f"English title has only {len(words)} word(s), requires at least 2: '{english_title}'")
        
        baseline_valid = len(reasons) == 0
        return baseline_valid, reasons