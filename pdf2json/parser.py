"""Baseline PDF text extraction using PyMuPDF."""

from typing import List, Tuple, Dict, Any
import fitz  # PyMuPDF
import re


class PDFTextExtractor:
    """Extracts raw text and structure from PDF files."""
    
    def __init__(self, pdf_path: str):
        """Initialize PDF extractor.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.doc: fitz.Document = None
        self._header_footer_lines: set = None
    
    def __enter__(self):
        """Context manager entry."""
        self.doc = fitz.open(self.pdf_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.doc:
            self.doc.close()
    
    def extract_baseline_text(self) -> str:
        """Extract baseline text content from PDF for QA comparison.
        
        Returns:
            Complete text content as a single string
        """
        if not self.doc:
            raise ValueError("PDF document not open. Use context manager.")
        
        text_parts = []
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            text = page.get_text()
            text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def _detect_header_footer_lines(self, all_lines: List[Dict[str, Any]], threshold: float = 0.5) -> set:
        """Detect header/footer lines by high repetition across pages.
        
        Args:
            all_lines: List of line dictionaries
            threshold: Minimum fraction of pages a line must appear on to be considered header/footer
            
        Returns:
            Set of normalized line texts that are headers/footers
        """
        line_counts: Dict[str, int] = {}
        page_lines: Dict[int, set] = {}
        
        for line in all_lines:
            normalized = line['text'].strip()
            if len(normalized) < 3:  # Skip very short lines
                continue
            page = line['page']
            if page not in page_lines:
                page_lines[page] = set()
            page_lines[page].add(normalized)
            line_counts[normalized] = line_counts.get(normalized, 0) + 1
        
        total_pages = len(page_lines)
        if total_pages == 0:
            return set()
        
        header_footer = set()
        for line_text, count in line_counts.items():
            if count / total_pages >= threshold:
                header_footer.add(line_text)
        
        return header_footer
    
    def extract_positioned_lines(self) -> List[Dict[str, Any]]:
        """Extract text as positioned lines/blocks with bbox information.
        
        Reconstructs reading order for RTL: sort by y (top->bottom), then x (right->left).
        
        Returns:
            List of line dictionaries: {page, y, x, text, bbox}
        """
        if not self.doc:
            raise ValueError("PDF document not open. Use context manager.")
        
        all_lines: List[Dict[str, Any]] = []
        
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            
            # Get text blocks with position information
            blocks = page.get_text("dict")
            
            # Extract lines from blocks
            for block in blocks.get("blocks", []):
                if "lines" not in block:
                    continue
                
                for line in block.get("lines", []):
                    if "spans" not in line:
                        continue
                    
                    # Combine spans in the line
                    line_text_parts = []
                    bbox = None
                    
                    for span in line.get("spans", []):
                        if "text" in span:
                            text = span.get("text", "").strip()
                            if text:
                                line_text_parts.append(text)
                        
                        # Get bbox from first span
                        if bbox is None and "bbox" in span:
                            bbox = span["bbox"]
                    
                    if not line_text_parts:
                        continue
                    
                    line_text = " ".join(line_text_parts)
                    
                    # Normalize whitespace
                    line_text = re.sub(r'\s+', ' ', line_text).strip()
                    
                    if not line_text:
                        continue
                    
                    # Get position (use bbox if available, otherwise from line)
                    if bbox:
                        x = bbox[0]  # Left
                        y = bbox[1]  # Top
                    elif "bbox" in line:
                        bbox = line["bbox"]
                        x = bbox[0]
                        y = bbox[1]
                    else:
                        x = 0
                        y = 0
                    
                    all_lines.append({
                        "page": page_num + 1,
                        "y": y,
                        "x": x,
                        "text": line_text,
                        "bbox": bbox or [x, y, x + 100, y + 10]
                    })
        
        # Sort by page, then y (top to bottom), then x (right to left for RTL)
        all_lines.sort(key=lambda l: (l["page"], l["y"], -l["x"]))
        
        # Detect and remove header/footer lines
        if len(all_lines) > 0:
            header_footer = self._detect_header_footer_lines(all_lines)
            all_lines = [line for line in all_lines if line["text"].strip() not in header_footer]
        
        return all_lines
    
    def extract_text_with_structure(self) -> List[Tuple[int, str, dict]]:
        """Extract text with page numbers and basic structure information.
        
        Returns:
            List of tuples: (page_number, text, metadata_dict)
        """
        if not self.doc:
            raise ValueError("PDF document not open. Use context manager.")
        
        # Use positioned lines for better structure
        positioned_lines = self.extract_positioned_lines()
        
        # Group by page
        structured_text = []
        current_page = None
        page_text_lines = []
        
        for line in positioned_lines:
            page = line["page"]
            if current_page != page:
                if current_page is not None:
                    structured_text.append((current_page, "\n".join(page_text_lines), {}))
                current_page = page
                page_text_lines = []
            page_text_lines.append(line["text"])
        
        if current_page is not None:
            structured_text.append((current_page, "\n".join(page_text_lines), {}))
        
        return structured_text
    
    def get_page_count(self) -> int:
        """Get total number of pages in PDF.
        
        Returns:
            Number of pages
        """
        if not self.doc:
            raise ValueError("PDF document not open. Use context manager.")
        return len(self.doc)
    
    def extract_tables_from_page(self, page_num: int) -> List[List[List[str]]]:
        """Extract tables from a specific page using PyMuPDF table detection.
        
        Args:
            page_num: Page number (1-indexed)
            
        Returns:
            List of tables, where each table is a list of rows, each row is a list of cells
        """
        if not self.doc:
            raise ValueError("PDF document not open. Use context manager.")
        
        if page_num < 1 or page_num > len(self.doc):
            return []
        
        page = self.doc[page_num - 1]  # Convert to 0-indexed
        
        # Try to find tables on the page
        # PyMuPDF has basic table detection, but may need refinement
        tables = []
        try:
            # Get text blocks
            blocks = page.get_text("dict")
            
            # Simple approach: look for tab-separated or aligned text
            # This is a basic implementation; may need more sophisticated detection
            text = page.get_text()
            
            # Split by lines and look for potential table rows
            lines = text.split("\n")
            potential_table_rows = []
            
            for line in lines:
                # Look for lines with multiple columns (tab-separated or spaced)
                if "\t" in line or len(line.split()) > 3:
                    potential_table_rows.append(line)
            
            # Basic table construction (will be refined in extractor)
            if potential_table_rows:
                table = [row.split("\t") if "\t" in row else row.split() for row in potential_table_rows]
                if table:
                    tables.append(table)
        
        except Exception as e:
            # If table extraction fails, return empty list
            pass
        
        return tables

