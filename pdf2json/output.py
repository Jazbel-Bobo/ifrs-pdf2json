"""Output generation for JSON and HTML reports."""

import json
import re
from pathlib import Path
from typing import Optional, Dict
from pdf2json.models import StandardDocument, QADocument


class OutputGenerator:
    """Generates JSON and HTML output files."""
    
    def __init__(self, output_dir: str):
        """Initialize output generator.
        
        Args:
            output_dir: Output directory path
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_main_json(self, document: StandardDocument) -> Path:
        """Generate main JSON file.
        
        Args:
            document: StandardDocument to serialize
            
        Returns:
            Path to generated JSON file
        """
        output_path = self.output_dir / f"{document.standard_id}.json"
        
        # Convert to dict and serialize
        doc_dict = document.model_dump(mode='json', exclude_none=False)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(doc_dict, f, ensure_ascii=False, indent=2)
        
        return output_path
    
    def generate_qa_json(self, qa_document: QADocument) -> Path:
        """Generate QA JSON file.
        
        Args:
            qa_document: QADocument to serialize
            
        Returns:
            Path to generated JSON file
        """
        output_path = self.output_dir / f"{qa_document.standard_id}.qa.json"
        
        # Convert to dict and serialize
        qa_dict = qa_document.model_dump(mode='json', exclude_none=False)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(qa_dict, f, ensure_ascii=False, indent=2)
        
        return output_path
    
    def generate_html_report(self, document: StandardDocument, qa_document: Optional[QADocument] = None, baseline_text: Optional[str] = None) -> Path:
        """Generate HTML report.
        
        Args:
            document: StandardDocument to report on
            qa_document: Optional QADocument for QA information
            baseline_text: Optional baseline text for TOC detection
            
        Returns:
            Path to generated HTML file
        """
        output_path = self.output_dir / f"{document.standard_id}.report.html"
        
        html_content = self._generate_html_content(document, qa_document, baseline_text)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return output_path
    
    def _generate_html_content(self, document: StandardDocument, qa_document: Optional[QADocument], baseline_text: Optional[str] = None) -> str:
        """Generate HTML content for report."""
        
        # Determine if RTL (Hebrew present)
        is_rtl = bool(document.standard_title.hebrew)
        dir_attr = 'dir="rtl"' if is_rtl else ''
        
        html = f"""<!DOCTYPE html>
<html lang="he" {dir_attr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{document.standard_id} - Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            direction: {'rtl' if is_rtl else 'ltr'};
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-left: 4px solid #4CAF50;
            padding-left: 10px;
        }}
        h3 {{
            color: #777;
            margin-top: 20px;
        }}
        .section {{
            margin: 20px 0;
            padding: 15px;
            background-color: #f9f9f9;
            border-radius: 5px;
        }}
        .paragraph {{
            margin: 15px 0;
            padding: 15px;
            background-color: white;
            border-left: 3px solid #2196F3;
            border-radius: 3px;
        }}
        .paragraph-id {{
            font-weight: bold;
            color: #2196F3;
            font-size: 1.1em;
            display: block;
            margin-bottom: 8px;
        }}
        .paragraph-content {{
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .qa-section {{
            margin: 30px 0;
            padding: 20px;
            background-color: {'#d4edda' if qa_document and qa_document.passed else '#f8d7da'};
            border-radius: 5px;
            border: 2px solid {'#28a745' if qa_document and qa_document.passed else '#dc3545'};
        }}
        .qa-score {{
            font-size: 24px;
            font-weight: bold;
            color: {'#28a745' if qa_document and qa_document.passed else '#dc3545'};
        }}
        .issue {{
            color: #dc3545;
            margin: 5px 0;
        }}
        .warning {{
            color: #ffc107;
            margin: 5px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: {'right' if is_rtl else 'left'};
        }}
        th {{
            background-color: #4CAF50;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{document.standard_id}</h1>
"""
        
        # Add standard title
        if document.standard_title.hebrew or document.standard_title.english:
            html += "        <h2>Standard Title</h2>\n"
            if document.standard_title.hebrew:
                html += f"        <p><strong>Hebrew:</strong> {self._escape_html(document.standard_title.hebrew)}</p>\n"
            if document.standard_title.english:
                html += f"        <p><strong>English:</strong> {self._escape_html(document.standard_title.english)}</p>\n"
        
        # Add QA section if available
        if qa_document:
            html += f"""
        <div class="qa-section">
            <h2>Quality Assessment</h2>
            <div class="qa-score">Score: {qa_document.score:.2%} {'✓ PASSED' if qa_document.passed else '✗ FAILED'}</div>
            <p>Threshold: {qa_document.threshold:.2%}</p>
            
            <h3>Checks</h3>
            <ul>
"""
            for check_name, check in qa_document.checks.items():
                status = "✓" if check.passed else "✗"
                html += f"                <li>{status} {check.name}: {check.score:.2%}</li>\n"
            
            html += "            </ul>\n"
            
            if qa_document.issues:
                html += "            <h3>Issues</h3>\n            <ul>\n"
                for issue in qa_document.issues:
                    html += f"                <li class='issue'>{self._escape_html(issue)}</li>\n"
                html += "            </ul>\n"
            
            if qa_document.warnings:
                html += "            <h3>Warnings</h3>\n            <ul>\n"
                for warning in qa_document.warnings:
                    html += f"                <li class='warning'>{self._escape_html(warning)}</li>\n"
                html += "            </ul>\n"
            
            html += "        </div>\n"
        
        # Add flags section (TOC, front matter, appendices)
        html += "        <h2>Document Structure Flags</h2>\n"
        html += "        <ul>\n"
        
        # Check for TOC in baseline
        toc_detected = "תוכן עניינים" in baseline_text if baseline_text else False
        html += f"            <li>TOC detected: {'Yes' if toc_detected else 'No'}</li>\n"
        
        # Check for appendices
        appendices_detected = bool(document.appendix_A or document.appendix_B or document.appendix_C)
        html += f"            <li>Appendices detected: {'Yes' if appendices_detected else 'No'}</li>\n"
        if appendices_detected:
            appendix_list = []
            if document.appendix_A:
                appendix_list.append("A")
            if document.appendix_B:
                appendix_list.append("B")
            if document.appendix_C:
                appendix_list.append("C")
            html += f"            <li>Found appendices: {', '.join(appendix_list)}</li>\n"
        
        html += "        </ul>\n"
        
        # Add main content
        html += "        <h2>Main Content</h2>\n"
        for section in document.main.sections:
            html += f'        <div class="section">\n'
            html += f"            <h3>{self._escape_html(section.section_title)}</h3>\n"
            
            # Add paragraphs
            for para in section.paragraphs:
                html += f'            <div class="paragraph">\n'
                html += f'                <span class="paragraph-id">{para.paragraph_id}</span>\n'
                html += f'                <div class="paragraph-content">{self._escape_html(para.content)}</div>\n'
                html += f'            </div>\n'
            
            # Add subsections
            for sub in section.subsections:
                if sub.subsection_title:
                    html += f"            <h4>{self._escape_html(sub.subsection_title)}</h4>\n"
                for para in sub.paragraphs:
                    html += f'            <div class="paragraph">\n'
                    html += f'                <span class="paragraph-id">{para.paragraph_id}</span>\n'
                    html += f'                <div class="paragraph-content">{self._escape_html(para.content)}</div>\n'
                    html += f'            </div>\n'
            
            html += "        </div>\n"
        
        # Add appendices (primary normative content per SPEC 9.1)
        if document.appendix_A or document.appendix_B or document.appendix_C:
            html += "        <h2>Appendices (Primary Normative Content)</h2>\n"
            
            for appendix in [document.appendix_A, document.appendix_B, document.appendix_C]:
                if appendix:
                    html += f'        <div class="section">\n'
                    html += f"            <h3>Appendix {appendix.appendix_id}</h3>\n"
                    if appendix.title:
                        html += f"            <p><em>{self._escape_html(appendix.title)}</em></p>\n"
                    
                    for section in appendix.sections:
                        html += f"            <h4>{self._escape_html(section.section_title)}</h4>\n"
                        for para in section.paragraphs:
                            html += f'            <div class="paragraph">\n'
                            html += f'                <span class="paragraph-id">{para.paragraph_id}</span>\n'
                            html += f'                <div class="paragraph-content">{self._escape_html(para.content)}</div>\n'
                            html += f'            </div>\n'
                        for sub in section.subsections:
                            if sub.subsection_title:
                                html += f"            <h5>{self._escape_html(sub.subsection_title)}</h5>\n"
                            for para in sub.paragraphs:
                                html += f'            <div class="paragraph">\n'
                                html += f'                <span class="paragraph-id">{para.paragraph_id}</span>\n'
                                html += f'                <div class="paragraph-content">{self._escape_html(para.content)}</div>\n'
                                html += f'            </div>\n'
                    
                    html += "        </div>\n"
        
        # Add definitions
        if document.definitions:
            html += "        <h2>Definitions</h2>\n        <ul>\n"
            for definition in document.definitions:
                html += f"            <li><strong>{self._escape_html(definition.term)}</strong>: "
                html += f"{self._escape_html(definition.definition)}</li>\n"
            html += "        </ul>\n"
        
        # Add exclusions
        if document.exclusions and document.exclusions.untranslated_sections:
            html += "        <h2>Excluded Sections</h2>\n        <ul>\n"
            for exclusion in document.exclusions.untranslated_sections:
                html += f"            <li>Page {exclusion.page}: {self._escape_html(exclusion.section)} "
                html += f"({self._escape_html(exclusion.reason)})</li>\n"
            html += "        </ul>\n"
        
        # Add debug section: paragraph statistics and issues
        all_paragraphs = []
        paragraph_pages: Dict[str, int] = {}  # Track which page each paragraph appears on
        
        for section in document.main.sections:
            for para in section.paragraphs:
                all_paragraphs.append(para)
            for sub in section.subsections:
                for para in sub.paragraphs:
                    all_paragraphs.append(para)
        
        html += "        <h2>Debug: Paragraph Detection</h2>\n"
        html += f"        <p><strong>Total paragraphs found:</strong> {len(all_paragraphs)}</p>\n"
        
        if all_paragraphs:
            # Extract paragraph numbers for analysis
            para_numbers = []
            for para in all_paragraphs:
                if ":" in para.paragraph_id:
                    num_part = para.paragraph_id.split(":")[1]
                    match = re.match(r'^(\d+)([A-Z]+)?$', num_part)
                    if match:
                        num = int(match.group(1))
                        suffix = match.group(2) or ""
                        para_numbers.append((num, suffix, para.paragraph_id))
            
            # Detect jumps and duplicates
            jumps: List[str] = []
            duplicates: List[str] = []
            seen_ids: Dict[str, int] = {}
            
            prev_num = None
            for num, suffix, para_id in sorted(para_numbers, key=lambda x: (x[0], x[1])):
                # Check for duplicates
                if para_id in seen_ids:
                    duplicates.append(f"{para_id} (appears {seen_ids[para_id] + 1} times)")
                else:
                    seen_ids[para_id] = 1
                
                # Check for jumps
                if prev_num is not None:
                    jump = num - prev_num
                    if jump > 5:  # Significant jump
                        jumps.append(f"Jump from {prev_num} to {num} (gap of {jump})")
                prev_num = num
            
            # Show first 20 paragraph IDs
            html += "        <h3>First 20 Paragraph IDs</h3>\n"
            html += "        <table>\n"
            html += "            <thead>\n"
            html += "                <tr><th>Paragraph ID</th><th>Content Preview (first 80 chars)</th></tr>\n"
            html += "            </thead>\n"
            html += "            <tbody>\n"
            
            for para in all_paragraphs[:20]:
                preview = para.content[:80] if para.content else "(empty)"
                if len(para.content) > 80:
                    preview += "..."
                html += f"                <tr>\n"
                html += f"                    <td><code>{self._escape_html(para.paragraph_id)}</code></td>\n"
                html += f"                    <td>{self._escape_html(preview)}</td>\n"
                html += f"                </tr>\n"
            
            html += "            </tbody>\n"
            html += "        </table>\n"
            
            if len(all_paragraphs) > 20:
                html += f"        <p><em>(Showing first 20 of {len(all_paragraphs)} paragraphs)</em></p>\n"
            
            # Show jumps and duplicates
            if jumps:
                html += "        <h3>Paragraph Numbering Jumps</h3>\n"
                html += "        <ul>\n"
                for jump in jumps[:10]:  # Limit to first 10
                    html += f"            <li class='warning'>{self._escape_html(jump)}</li>\n"
                html += "        </ul>\n"
            
            if duplicates:
                html += "        <h3>Duplicate Paragraph IDs</h3>\n"
                html += "        <ul>\n"
                for dup in duplicates[:10]:  # Limit to first 10
                    html += f"            <li class='issue'>{self._escape_html(dup)}</li>\n"
                html += "        </ul>\n"
        else:
            html += "        <p class='issue'><strong>No paragraphs found!</strong></p>\n"
        
        html += """
    </div>
</body>
</html>
"""
        
        return html
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (text.replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;")
                   .replace("'", "&#x27;"))

