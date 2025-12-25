"""QA validation module."""

import re
from typing import Dict, List, Tuple, Set
from pdf2json.models import StandardDocument, QADocument, QACheck


class QAValidator:
    """Validates parsed documents against quality thresholds."""
    
    def __init__(self, threshold: float = 0.80):
        """Initialize QA validator.
        
        Args:
            threshold: Minimum score required to pass (default 0.80)
        """
        self.threshold = threshold
    
    def validate(self, document: StandardDocument, baseline_text: str) -> QADocument:
        """Run QA validation on a parsed document.
        
        Args:
            document: The parsed StandardDocument
            baseline_text: Baseline text extracted from PDF for comparison
            
        Returns:
            QADocument with validation results
        """
        checks: Dict[str, QACheck] = {}
        issues: List[str] = []
        warnings: List[str] = []
        
        # Check 0: TOC contamination (SPEC 13.2.2) - MUST FAIL if TOC appears in normative parts
        toc_contamination_score, toc_issues = self._check_toc_contamination(document, baseline_text)
        checks["toc_contamination"] = QACheck(
            name="TOC Contamination",
            score=toc_contamination_score,
            threshold=self.threshold,
            passed=toc_contamination_score >= self.threshold
        )
        issues.extend(toc_issues)
        # TOC contamination is a hard fail per SPEC
        if toc_contamination_score < 1.0:
            # This will cause overall failure
            pass
        
        # Check 1: Structure completeness
        structure_score = self._check_structure_completeness(document)
        checks["structure_completeness"] = QACheck(
            name="Structure Completeness",
            score=structure_score,
            threshold=self.threshold,
            passed=structure_score >= self.threshold
        )
        if structure_score < self.threshold:
            issues.append(f"Structure completeness below threshold: {structure_score:.2f} < {self.threshold:.2f}")
        
        # Check 2: Paragraph numbering
        para_score, para_issues = self._check_paragraph_numbering(document, baseline_text)
        checks["paragraph_numbering"] = QACheck(
            name="Paragraph Numbering",
            score=para_score,
            threshold=self.threshold,
            passed=para_score >= self.threshold
        )
        issues.extend(para_issues)
        
        # Check 3: Table detection (optional - don't penalize if none found and none in baseline)
        table_score, table_issues = self._check_table_detection(document, baseline_text)
        checks["table_detection"] = QACheck(
            name="Table Detection",
            score=table_score,
            threshold=self.threshold,
            passed=table_score >= self.threshold
        )
        # Only add issues if tables were expected but not found
        if table_issues and "may be valid" not in " ".join(table_issues).lower():
            issues.extend(table_issues)
        
        # Check 4: Definition extraction
        def_score, def_issues = self._check_definition_extraction(document)
        checks["definition_extraction"] = QACheck(
            name="Definition Extraction",
            score=def_score,
            threshold=self.threshold,
            passed=def_score >= self.threshold
        )
        issues.extend(def_issues)
        
        # Check 5: Footnote linking (optional - don't penalize if none found and none in baseline)
        footnote_score, footnote_issues = self._check_footnote_linking(document, baseline_text)
        checks["footnote_linking"] = QACheck(
            name="Footnote Linking",
            score=footnote_score,
            threshold=self.threshold,
            passed=footnote_score >= self.threshold
        )
        # Only add issues if footnotes were expected but not found
        if footnote_issues and "may be valid" not in " ".join(footnote_issues).lower():
            issues.extend(footnote_issues)
        
        # Calculate overall score (weighted average)
        # TOC contamination is a hard fail - if it fails, overall fails regardless
        toc_failed = "toc_contamination" in checks and not checks["toc_contamination"].passed
        
        weights = {
            "toc_contamination": 0.20,  # High weight for critical check
            "structure_completeness": 0.20,
            "paragraph_numbering": 0.20,
            "table_detection": 0.15,
            "definition_extraction": 0.15,
            "footnote_linking": 0.10
        }
        
        overall_score = sum(
            checks[key].score * weights.get(key, 0.0)
            for key in checks
        )
        
        all_passed = all(check.passed for check in checks.values())
        # TOC contamination is a hard fail per SPEC 13.2.2
        if toc_failed:
            passed = False
        else:
            passed = all_passed and overall_score >= self.threshold
        
        return QADocument(
            standard_id=document.standard_id,
            passed=passed,
            score=overall_score,
            threshold=self.threshold,
            checks=checks,
            issues=issues,
            warnings=warnings
        )
    
    def _check_structure_completeness(self, document: StandardDocument) -> float:
        """Check if document has expected structure elements.
        
        Returns:
            Score between 0.0 and 1.0
        """
        score = 1.0
        checks_passed = 0
        total_checks = 5
        
        # Check 1: Has standard_id
        if document.standard_id:
            checks_passed += 1
        else:
            score -= 0.2
        
        # Check 2: Has main content with sections
        if document.main and document.main.sections:
            checks_passed += 1
        else:
            score -= 0.2
        
        # Check 3: Has at least some paragraphs (including appendices)
        total_paragraphs = sum(
            len(section.paragraphs) + sum(len(sub.paragraphs) for sub in section.subsections)
            for section in document.main.sections
        )
        
        # Count appendices paragraphs (primary normative content per SPEC 9.1)
        appendix_paragraphs = 0
        for appendix in [document.appendix_A, document.appendix_B, document.appendix_C]:
            if appendix:
                appendix_paragraphs += sum(
                    len(section.paragraphs) + sum(len(sub.paragraphs) for sub in section.subsections)
                    for section in appendix.sections
                )
        
        total_paragraphs_all = total_paragraphs + appendix_paragraphs
        
        if total_paragraphs_all > 0:
            checks_passed += 1
        else:
            score -= 0.2
        
        # Check 4: Standard title completeness (SPEC 13.2.4)
        title_ok = False
        if document.standard_title:
            # Hebrew title MUST include standard number
            if document.standard_title.hebrew:
                # Check if number is in Hebrew title (e.g., "16" in "תקן חשבונאות בינלאומי 16 רכוש קבוע")
                if re.search(r'\d+', document.standard_title.hebrew):
                    title_ok = True
            # English title should be extracted if present on cover page
            if document.standard_title.english:
                # Check if it's more than just "International Accounting Standard X"
                if len(document.standard_title.english) > len("International Accounting Standard XX") + 5:
                    title_ok = True
        
        if title_ok:
            checks_passed += 1
        else:
            score -= 0.2
        
        # Check 5: Structure is not empty (including appendices)
        if total_paragraphs_all > 10:  # Reasonable minimum
            checks_passed += 1
        else:
            score -= 0.2
        
        return max(0.0, min(1.0, checks_passed / total_checks))
    
    def _extract_expected_paragraph_numbers(self, baseline_text: str, standard_id: str) -> Set[str]:
        """Extract expected paragraph numbers from baseline text using paragraph-start regex.
        
        Args:
            baseline_text: Baseline text from PDF
            standard_id: Standard identifier (e.g., "IAS_16")
            
        Returns:
            Set of normalized paragraph number strings (e.g., {"1", "2", "20", "20A", "29A"})
        """
        expected_numbers: Set[str] = set()
        
        # Use the same paragraph detection patterns as extractor
        lines = baseline_text.split("\n")
        
        # Pattern 1: Number followed by dot and optional Hebrew/Latin letter: "7.", "20א.", "29א."
        pattern1 = re.compile(r'^(\d{1,3})\s*\.?\s*([א-תA-Z])?\s*\.?\s*')
        # Pattern 2: Number followed by space and Hebrew/Latin letter: "20א ", "20A "
        pattern2 = re.compile(r'^(\d{1,3})([א-תA-Z])\s+')
        # Pattern 3: Number followed by dot and space: "7. ", "20. "
        pattern3 = re.compile(r'^(\d{1,3})\s*\.\s+')
        # Pattern 4: Plain number at start: "7 ", "20 "
        pattern4 = re.compile(r'^(\d{1,3})\s+')
        
        # Hebrew to Latin mapping (simplified - use first few common ones)
        hebrew_to_latin_map = {
            'א': 'A', 'ב': 'B', 'ג': 'C', 'ד': 'D', 'ה': 'E',
            'ו': 'V', 'ז': 'Z', 'ח': 'H', 'ט': 'T', 'י': 'I',
            'כ': 'K', 'ל': 'L', 'מ': 'M', 'נ': 'N', 'ס': 'S',
            'ע': 'O', 'פ': 'P', 'צ': 'Q', 'ק': 'Q', 'ר': 'R',
            'ש': 'SH', 'ת': 'TH'
        }
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            para_number = None
            para_suffix = None
            
            # Try patterns in order
            match1 = pattern1.match(line)
            if match1:
                para_number = match1.group(1)
                suffix_raw = match1.group(2)
                if suffix_raw:
                    para_suffix = hebrew_to_latin_map.get(suffix_raw, suffix_raw.upper())
                rest = line[match1.end():].strip()
                if rest and len(rest) > 2:
                    if para_suffix:
                        expected_numbers.add(f"{para_number}{para_suffix}")
                    else:
                        expected_numbers.add(para_number)
                continue
            
            match2 = pattern2.match(line)
            if match2:
                para_number = match2.group(1)
                suffix_raw = match2.group(2)
                para_suffix = hebrew_to_latin_map.get(suffix_raw, suffix_raw.upper())
                rest = line[match2.end():].strip()
                if rest and len(rest) > 2:
                    expected_numbers.add(f"{para_number}{para_suffix}")
                continue
            
            match3 = pattern3.match(line)
            if match3:
                para_number = match3.group(1)
                rest = line[match3.end():].strip()
                if rest and len(rest) > 2:
                    expected_numbers.add(para_number)
                continue
            
            match4 = pattern4.match(line)
            if match4:
                para_number = match4.group(1)
                rest = line[match4.end():].strip()
                if rest and len(rest) > 5 and not rest[0].isdigit():
                    expected_numbers.add(para_number)
        
        return expected_numbers
    
    def _check_toc_contamination(self, document: StandardDocument, baseline_text: str) -> Tuple[float, List[str]]:
        """Check for TOC contamination in normative parts (SPEC 13.2.2).
        
        Returns:
            Tuple of (score, issues) - score 1.0 if no contamination, 0.0 if found
        """
        issues: List[str] = []
        toc_pattern = re.compile(r'תוכן\s+עניינים', re.IGNORECASE)
        
        # Check main content
        for section in document.main.sections:
            for para in section.paragraphs:
                if toc_pattern.search(para.content):
                    issues.append(f"TOC content found in main content paragraph {para.paragraph_id}")
                    return 0.0, issues
            for sub in section.subsections:
                for para in sub.paragraphs:
                    if toc_pattern.search(para.content):
                        issues.append(f"TOC content found in main content paragraph {para.paragraph_id}")
                        return 0.0, issues
        
        # Check appendices (also normative)
        for appendix in [document.appendix_A, document.appendix_B, document.appendix_C]:
            if appendix:
                for section in appendix.sections:
                    for para in section.paragraphs:
                        if toc_pattern.search(para.content):
                            issues.append(f"TOC content found in appendix {appendix.appendix_id} paragraph {para.paragraph_id}")
                            return 0.0, issues
                    for sub in section.subsections:
                        for para in sub.paragraphs:
                            if toc_pattern.search(para.content):
                                issues.append(f"TOC content found in appendix {appendix.appendix_id} paragraph {para.paragraph_id}")
                                return 0.0, issues
        
        return 1.0, issues
    
    def _check_paragraph_numbering(self, document: StandardDocument, baseline_text: str) -> Tuple[float, List[str]]:
        """Check paragraph numbering consistency.
        
        Derives expected paragraph numbers from baseline and scores based on coverage
        and monotonic ordering. Includes appendices in counts per SPEC 9.1.
        
        Returns:
            Tuple of (score, issues)
        """
        issues: List[str] = []
        paragraph_ids = []
        paragraph_numbers = []  # Store (number, suffix, page) for ordering check
        
        def collect_paragraph_ids(section):
            for para in section.paragraphs:
                paragraph_ids.append(para.paragraph_id)
                # Extract number from ID (e.g., "IAS_16:20A" -> ("20", "A"))
                if ":" in para.paragraph_id:
                    num_part = para.paragraph_id.split(":")[1]
                    # Try to split number and suffix
                    match = re.match(r'^(\d+)([A-Z]+)?$', num_part)
                    if match:
                        num = int(match.group(1))
                        suffix = match.group(2) or ""
                        paragraph_numbers.append((num, suffix, 0))  # Page not tracked here
        
        # Collect from main content
        for section in document.main.sections:
            collect_paragraph_ids(section)
        
        # Collect from appendices (primary normative content per SPEC 9.1)
        for appendix in [document.appendix_A, document.appendix_B, document.appendix_C]:
            if appendix:
                for section in appendix.sections:
                    collect_paragraph_ids(section)
        
        # Check 1: Must have paragraphs (including appendices per SPEC 9.1)
        if not paragraph_ids:
            return 0.0, ["No paragraphs found"]
        
        # Check 1.5: Validate that IAS_16:1 and IAS_16:2 exist in main content (not appendices)
        main_paragraph_ids = [
            para.paragraph_id
            for section in document.main.sections
            for para in section.paragraphs
        ]
        for section in document.main.sections:
            for subsec in section.subsections:
                main_paragraph_ids.extend([para.paragraph_id for para in subsec.paragraphs])
        
        standard_prefix = f"{document.standard_id}:"
        expected_first_ids = [f"{standard_prefix}1", f"{standard_prefix}2"]
        found_first = sum(1 for expected_id in expected_first_ids if expected_id in main_paragraph_ids)
        if found_first == 0 and len(main_paragraph_ids) > 0:
            issues.append(f"Expected first paragraphs ({', '.join(expected_first_ids)}) not found in main content - main content may not start correctly")
        
        # Check 2: Extract expected paragraph numbers from baseline
        expected_numbers = self._extract_expected_paragraph_numbers(baseline_text, document.standard_id)
        
        # Extract found paragraph numbers (normalized)
        found_numbers: Set[str] = set()
        for para_id in paragraph_ids:
            if ":" in para_id:
                num_part = para_id.split(":")[1]
                found_numbers.add(num_part)
        
        # Check 3: Coverage - how many expected numbers were found
        if expected_numbers:
            coverage = len(found_numbers & expected_numbers) / len(expected_numbers)
            if coverage < 0.5:
                issues.append(f"Low coverage: found {len(found_numbers & expected_numbers)}/{len(expected_numbers)} expected paragraph numbers")
        else:
            # If no expected numbers found in baseline, use found numbers as baseline
            coverage = 1.0 if found_numbers else 0.0
        
        # Check 4: Check for duplicate IDs
        unique_ids = set(paragraph_ids)
        if len(unique_ids) < len(paragraph_ids):
            duplicates = len(paragraph_ids) - len(unique_ids)
            issues.append(f"Found {duplicates} duplicate paragraph IDs")
            return max(0.1, 0.5 - (duplicates / len(paragraph_ids))), issues
        
        # Check 5: Monotonic ordering (check if numbers are generally increasing)
        if paragraph_numbers:
            # Sort by number, then suffix
            sorted_numbers = sorted(paragraph_numbers, key=lambda x: (x[0], x[1]))
            ordering_score = 1.0
            
            # Check for major jumps or reversals
            prev_num = None
            for num, suffix, _ in sorted_numbers:
                if prev_num is not None:
                    if num < prev_num:
                        ordering_score -= 0.2
                        issues.append(f"Non-monotonic ordering: {prev_num} -> {num}")
                    elif num > prev_num + 10:  # Large jump
                        ordering_score -= 0.1
                prev_num = num
            
            ordering_score = max(0.0, ordering_score)
        else:
            ordering_score = 0.5  # Neutral if can't determine
        
        # Check 6: ID format consistency
        standard_prefix = f"{document.standard_id}:"
        valid_format = sum(1 for pid in paragraph_ids if pid.startswith(standard_prefix))
        format_score = valid_format / len(paragraph_ids) if paragraph_ids else 0.0
        
        if format_score < 1.0:
            issues.append(f"Only {valid_format}/{len(paragraph_ids)} paragraph IDs have correct format")
        
        # Calculate overall score: weighted average
        # Coverage: 40%, Format: 30%, Ordering: 30%
        score = (coverage * 0.4) + (format_score * 0.3) + (ordering_score * 0.3)
        
        return score, issues
    
    def _check_table_detection(self, document: StandardDocument, baseline_text: str) -> Tuple[float, List[str]]:
        """Check table detection quality.
        
        Returns:
            Tuple of (score, issues)
        """
        issues: List[str] = []
        total_tables = 0
        valid_tables = 0
        
        def count_tables(section):
            nonlocal total_tables, valid_tables
            for para in section.paragraphs:
                for table in para.tables:
                    total_tables += 1
                    if table.headers or table.rows:
                        valid_tables += 1
            for sub in section.subsections:
                for para in sub.paragraphs:
                    for table in para.tables:
                        total_tables += 1
                        if table.headers or table.rows:
                            valid_tables += 1
        
        for section in document.main.sections:
            count_tables(section)
        
        if total_tables == 0:
            # Check if tables are mentioned in baseline (simple heuristic)
            has_table_indicators = any(indicator in baseline_text.lower() for indicator in ["table", "טבלה", "جدول"])
            if not has_table_indicators:
                # No tables found and no table indicators in baseline - likely valid
                return 0.9, ["No tables detected (none found in baseline)"]
            else:
                return 0.5, ["No tables detected but table indicators found in baseline"]
        
        score = valid_tables / total_tables if total_tables > 0 else 0.0
        
        if score < 1.0:
            issues.append(f"Only {valid_tables}/{total_tables} tables have valid structure")
        
        return score, issues
    
    def _check_definition_extraction(self, document: StandardDocument) -> Tuple[float, List[str]]:
        """Check definition extraction quality.
        
        Returns:
            Tuple of (score, issues)
        """
        issues: List[str] = []
        definitions = document.definitions
        
        if not definitions:
            return 0.5, ["No definitions extracted (may be valid)"]
        
        # Check that definitions have terms and content
        valid_definitions = sum(
            1 for d in definitions
            if d.term and d.definition
        )
        
        score = valid_definitions / len(definitions) if definitions else 0.0
        
        if score < 1.0:
            issues.append(f"Only {valid_definitions}/{len(definitions)} definitions are complete")
        
        return score, issues
    
    def _check_footnote_linking(self, document: StandardDocument, baseline_text: str) -> Tuple[float, List[str]]:
        """Check footnote linking quality.
        
        Returns:
            Tuple of (score, issues)
        """
        issues: List[str] = []
        total_footnotes = 0
        linked_footnotes = 0
        
        def count_footnotes(section):
            nonlocal total_footnotes, linked_footnotes
            for para in section.paragraphs:
                for footnote in para.footnotes:
                    total_footnotes += 1
                    if footnote.referenced_paragraph_id == para.paragraph_id:
                        linked_footnotes += 1
            for sub in section.subsections:
                for para in sub.paragraphs:
                    for footnote in para.footnotes:
                        total_footnotes += 1
                        if footnote.referenced_paragraph_id == para.paragraph_id:
                            linked_footnotes += 1
        
        for section in document.main.sections:
            count_footnotes(section)
        
        if total_footnotes == 0:
            # Check if footnotes are mentioned in baseline (simple heuristic)
            has_footnote_indicators = any(indicator in baseline_text.lower() for indicator in ["footnote", "הערת שוליים", "note"])
            if not has_footnote_indicators:
                # No footnotes found and no footnote indicators in baseline - likely valid
                return 0.9, ["No footnotes detected (none found in baseline)"]
            else:
                return 0.5, ["No footnotes detected but footnote indicators found in baseline"]
        
        score = linked_footnotes / total_footnotes if total_footnotes > 0 else 0.0
        
        if score < 1.0:
            issues.append(f"Only {linked_footnotes}/{total_footnotes} footnotes are properly linked")
        
        return score, issues

