"""Data models for PDF to JSON conversion."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class StandardTitle(BaseModel):
    """Standard title in Hebrew and/or English."""
    hebrew: Optional[str] = None
    english: Optional[str] = None


class Clause(BaseModel):
    """A clause within a paragraph (e.g., 16(a), 16(b))."""
    clause_id: str = Field(..., description="Human-readable clause ID (e.g., IAS_16:16(a))")
    content: str


class Table(BaseModel):
    """A table embedded in a paragraph or section."""
    table_id: Optional[str] = None
    headers: List[str] = []
    rows: List[List[str]] = []


class Footnote(BaseModel):
    """A footnote linked to a paragraph."""
    footnote_id: str = Field(..., description="Footnote reference ID")
    content: str
    referenced_paragraph_id: str = Field(..., description="Paragraph ID this footnote belongs to")


class Paragraph(BaseModel):
    """A paragraph with optional clauses, tables, and footnotes."""
    paragraph_id: str = Field(..., description="Human-readable paragraph ID (e.g., IAS_16:16, IAS_16:20A)")
    content: str
    clauses: List[Clause] = []
    tables: List[Table] = []
    footnotes: List[Footnote] = []


class Subsection(BaseModel):
    """A subsection containing paragraphs."""
    subsection_title: Optional[str] = None
    paragraphs: List[Paragraph] = []


class Section(BaseModel):
    """A section containing subsections and/or paragraphs."""
    section_title: str
    paragraphs: List[Paragraph] = []
    subsections: List[Subsection] = []


class MainContent(BaseModel):
    """Main content section of the standard."""
    sections: List[Section] = []


class Appendix(BaseModel):
    """An appendix section (A, B, C, etc.)."""
    appendix_id: str = Field(..., description="Appendix identifier (e.g., A, B, C)")
    title: Optional[str] = None
    sections: List[Section] = []


class Definition(BaseModel):
    """A definition extracted from the standard."""
    term: str
    definition: str
    referenced_from: List[str] = Field(default_factory=list, description="Paragraph IDs where this definition is referenced")


class Exclusion(BaseModel):
    """An excluded untranslated section."""
    page: int
    section: str
    reason: str


class Exclusions(BaseModel):
    """Record of excluded sections."""
    untranslated_sections: List[Exclusion] = []


class StandardDocument(BaseModel):
    """Complete structured document for a standard."""
    standard_id: str = Field(..., description="Standard identifier (e.g., IAS_16)")
    standard_title: StandardTitle
    main: MainContent
    appendix_A: Optional[Appendix] = None
    appendix_B: Optional[Appendix] = None
    appendix_C: Optional[Appendix] = None
    definitions: List[Definition] = []
    exclusions: Exclusions = Field(default_factory=Exclusions)


# QA Models

class QACheck(BaseModel):
    """Individual QA check result."""
    name: str
    score: float = Field(..., ge=0.0, le=1.0, description="Score between 0.0 and 1.0")
    threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    passed: bool


class QADocument(BaseModel):
    """QA assessment document."""
    standard_id: str
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0, description="Overall QA score")
    threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    checks: Dict[str, QACheck] = Field(default_factory=dict)
    issues: List[str] = []
    warnings: List[str] = []

