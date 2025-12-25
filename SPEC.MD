# SPEC_EN.md — ifrs-pdf2json (Hebrew RTL IFRS/IAS PDF → Structured JSON)

## 0) Mission
Convert Hebrew RTL IFRS/IAS PDFs (text-layer) into high-quality, deterministic, *normative* JSON per standard, suitable for a RAG tutor that must answer with correct paragraph references.

The tool is **fail-closed**:
- If requirements are not met → still output the best candidate + QA + HTML report, but return a non-zero exit code.

---

## 1) Input assumptions
1. PDFs are Hebrew RTL.
2. PDFs have a text layer (no OCR in v1).
3. Documents may contain tables, footnotes, and appendices.

---

## 2) Normative policy: what is allowed into the knowledge base
Not all PDF text is usable for answering accounting questions. The parser must classify content into semantic buckets:

### 2.1 Semantic buckets (MUST)
1) **front_matter**
   - Cover page, version notes, administrative text, etc.

2) **toc**
   - Table of Contents ("תוכן עניינים") and similar navigation lists.

3) **body** (normative)
   - The main normative content of the standard (sections/subsections/numbered paragraphs).

4) **appendices** (normative, primary)
   - Appendix A/B/C… are **primary normative sources**, not secondary.
   - They are separate parts only structurally, not by importance.

5) **excluded**
   - Untranslated sections, irrelevant publisher material, etc.

### 2.2 RAG inclusion rules (MUST)
- `body` + `appendices` → included in retrieval and allowed for answers.
- `front_matter` + `toc` → never included in retrieval; never cited as normative.
- `excluded` → never included in retrieval; MUST be logged as exclusions metadata.

---

## 3) Normative start boundary (MUST)
The normative `body` begins ONLY when one of these occurs:
- A heading equivalent to “מטרת התקן” followed by a first numbered paragraph; OR
- The first valid numbered paragraph marker is detected (often `.1`, `1.`, or `1` depending on publisher layout).

Any text before the normative start is NOT body content and MUST NOT be emitted as paragraphs.

---

## 4) Legal structure hierarchy (MUST)
The only valid hierarchy is:

Standard
└── part (body / appendix_A / appendix_B / appendix_C / ...)
    └── section (primary heading)
        └── subsection (secondary heading, optional)
            └── paragraph (numbered)
                ├── clauses (sub-items like (a)/(b) or (i)/(ii) or (א)/(ב))
                ├── footnotes (editor notes)
                └── tables (structured tables)

Rules:
- Primary heading: bold + long underline rule (publisher feature).
- Secondary heading: bold without underline rule.
- Paragraphs MUST have valid paragraph numbers.
- Footnotes are never standalone paragraphs.

---

## 5) Paragraph numbering and IDs (MUST)

### 5.1 Valid paragraph number forms
- Integer: `8`
- Integer + Hebrew letter: `8א`, `8ב`, ...
- Decimal: `8.1`, `8.1.1`
- Combined: `8א.1` (only if present in document)

### 5.2 Human-readable IDs
Each paragraph MUST have a stable, readable ID:

- `paragraph_id` (canonical): `<STANDARD_ID>:<TOKEN_CANONICAL>`
- `paragraph_id_display` (display): `<STANDARD_ID>:<TOKEN_AS_IN_PDF>`

Examples:
- `IAS_16:16` (both)
- `IAS_16:20A` (canonical) and `IAS_16:20א` (display)

Canonical mapping rule:
- Hebrew letters map to Latin letters for canonical IDs: א→A, ב→B, ג→C, … (consistent mapping must be defined and stable).

### 5.3 Continuity and ordering
- Paragraphs are generally sequential.
- Duplicates are forbidden.
- Large ordering anomalies are QA issues (warning or fail depending on severity).

---

## 6) Clauses (sub-items) (MUST)
Clause markers may be:
- Hebrew: `(א)`, `(ב)`, ...
- Roman: `(i)`, `(ii)`, `(iii)`...

Rules:
- Clauses are children of a paragraph.
- Clause IDs are readable: `IAS_16:16(a)` or `IAS_16:16(i)`.
- Clauses must not replace paragraph numbering.

---

## 7) Footnotes / editor notes (MUST)
Footnotes appear as:
- in-text reference marker
- corresponding note at the bottom of the page under a partial horizontal rule.

Rules:
- Footnotes are allowed in the knowledge base as secondary normative content.
- Footnotes MUST be linked to the referencing paragraph/clause when possible.
- If linking is uncertain → store as unlinked with page anchor and emit QA warning.
- Footnotes must not be silently merged into paragraph text without marking.

---

## 8) Tables (MUST)
Rules:
- Tables must be preserved as structured data: rows/columns/cells.
- Silent flattening of a detected table into plain text is forbidden.
- If true structure cannot be extracted reliably:
  - output `node_type="table"` with `table_parse_mode="fallback"`
  - QA must flag the fallback and reduce score.

---

## 9) Appendices (MUST)
### 9.1 Appendices are primary normative sources
Appendix A/B/C… are as authoritative as the body.

### 9.2 Appendix numbering
- Appendix B/C paragraphs may be labeled like: `ב1`, `ב2` / `ג1`, `ג2`, etc.
- Canonical IDs must be stable:
  - `IAS_16:B1` canonical, `IAS_16:ב1` display
  - `IAS_16:C3` canonical, `IAS_16:ג3` display

---

## 10) Definitions (MUST/SHOULD)
The tool SHOULD extract definitions as a separate `definitions[]` list when a definitions appendix exists.

Definition fields:
- term_he, term_en (if present), definition_text
- source_reference (paragraph_id or appendix location)
- optionally referenced_from paragraph ids

Rules:
- If a definitions appendix is detected → definitions[] should be populated.
- If Appendix A is not a dictionary layout in a given standard → it may be treated as normal appendix content; definitions[] may be empty with a QA warning (not necessarily a fail).

---

## 11) Untranslated / excluded content (MUST)
Any content that is not translated to Hebrew or is irrelevant publisher material MUST be:
- excluded from normative parts
- logged in `exclusions[]` with:
  - reason (untranslated / irrelevant / other)
  - detected_heading (if any)
  - page_range (if available)

---

## 12) Output format (JSON per standard) (MUST)
For each standard produce:
- `<out>/<STANDARD_ID>.json`
- `<out>/<STANDARD_ID>.qa.json`
- `<out>/<STANDARD_ID>.report.html`

Top-level JSON MUST include:
- schema_version
- standard_id (e.g., IAS_16)
- standard_title: { hebrew, english }
- parts[] where each part has:
  - part_id: "body" / "appendix_A" / ...
  - sections hierarchy
- definitions[]
- exclusions[]

---

## 13) QA as hard gate (MUST)

### 13.1 fix command behavior
`fix` MUST:
- run one or more parsing strategies
- run QA on each candidate
- return exit code 0 ONLY if thresholds are met
- otherwise output best candidate + QA + HTML report and return non-zero exit

### 13.2 Minimum QA checks (v1)
1) Schema validation MUST pass.
2) TOC contamination: if "תוכן עניינים" content appears inside any normative part → FAIL.
3) Paragraph existence: body must contain numbered paragraphs; each detected appendix must contain paragraphs → FAIL if zero.
4) Title completeness:
   - Hebrew standard title MUST include the standard number (e.g., 16).
   - If English title exists on cover page, it MUST be extracted; otherwise english may be null with warning.
5) No duplicate paragraph_id within the same part → FAIL.
6) Table integrity: detected tables must not be silently flattened → FAIL.
7) Footnote linking: if footnotes are detected, linking coverage should be reported; low coverage is at least a warning.

### 13.3 HTML report MUST show
- PASS/FAIL + overall score + thresholds
- paragraph counts per part
- first 20 paragraph_ids
- flags: toc detected, front matter detected, appendices detected
- top issues/warnings with examples

---

## 14) Guiding principle
Prefer excluding uncertain text over including wrong text.
Correctness > completeness.
Regression on a golden set is required before broad ingestion.
