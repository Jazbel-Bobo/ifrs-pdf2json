# IFRS PDF to JSON Converter

A tool for converting Hebrew RTL IFRS/IAS PDFs (with text layers) into structured JSON files, QA reports, and HTML reports.

## Installation

1. Create and activate a virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Command

```bash
python -m pdf2json fix "<PDF_PATH>" --out out
```

### Help

```bash
python -m pdf2json --help
```

## Output Files

For each processed PDF (e.g., `IAS_16.pdf`), the tool generates:

1. **Main JSON** (`IAS_16.json`): Structured content with sections, paragraphs, tables, definitions, and footnotes
2. **QA JSON** (`IAS_16.qa.json`): Quality assessment with validation scores and issues
3. **HTML Report** (`IAS_16.report.html`): Human-readable report showing the extracted structure

## QA Gates

The `fix` command runs quality checks. It will:
- Exit with code 0 only if all QA thresholds pass
- If QA fails, output the best candidate and HTML report, then exit with a non-zero code

## Features

- Structure-first parsing: correct paragraph numbering, headings, subsections
- Appendices separated (Main, Appendix A/B/C...)
- Definitions extracted into a separate list with back-references
- Footnotes preserved and linked to paragraphs
- Tables preserved as structured data (rows/cols/cells)
- Untranslated sections excluded but recorded in metadata

## Requirements

- Python 3.8+
- Windows-compatible (tested on Windows 10+)
- PDFs must have text layers (no OCR support)

