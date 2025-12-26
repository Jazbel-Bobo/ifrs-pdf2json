"""CLI commands using Typer."""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import typer
from pdf2json.parser import PDFTextExtractor
from pdf2json.extractor import Extractor
from pdf2json.qa import QAValidator
from pdf2json.output import OutputGenerator

app = typer.Typer(help="IFRS PDF to JSON Converter")


def extract_standard_id(pdf_path: str) -> str:
    """Extract standard ID from PDF filename.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Standard ID (e.g., "IAS_16")
    """
    filename = Path(pdf_path).stem
    # Try to extract IAS_16, IFRS_15, etc. from filename
    import re
    match = re.search(r'(IAS|IFRS)[_\s]*(\d+)', filename, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}_{match.group(2)}"
    # Fallback: use filename
    return filename.replace(" ", "_").replace("-", "_")


@app.command()
def fix(
    pdf_path: str = typer.Argument(..., help="Path to the PDF file"),
    out: str = typer.Option("out", "--out", "-o", help="Output directory"),
    threshold: float = typer.Option(0.80, "--threshold", "-t", help="QA threshold (0.0-1.0)"),
):
    """Convert PDF to JSON with QA validation.
    
    This command:
    1. Extracts baseline text from PDF
    2. Parses structure using available strategies
    3. Runs QA validation
    4. If QA passes: outputs JSON files and HTML report, exits with code 0
    5. If QA fails: outputs best candidate + HTML report, exits with non-zero code
    """
    # Validate PDF path
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        typer.echo(f"Error: PDF file not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    
    if not pdf_file.suffix.lower() == ".pdf":
        typer.echo(f"Error: Not a PDF file: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    
    # Extract standard ID
    standard_id = extract_standard_id(str(pdf_path))
    typer.echo(f"Processing {standard_id} from {pdf_path}")
    
    # Initialize components
    output_gen = OutputGenerator(out)
    validator = QAValidator(threshold=threshold)
    extractor = Extractor()
    
    best_document = None
    best_qa = None
    best_confidence = 0.0
    
    # Step 1: Baseline extraction
    typer.echo("Step 1: Extracting baseline text...")
    try:
        with PDFTextExtractor(str(pdf_path)) as pdf_extractor:
            baseline_text = pdf_extractor.extract_baseline_text()
            typer.echo(f"[OK] Extracted {len(baseline_text)} characters")
            
            # Step 2 & 3: Try parsing strategies in loop until QA passes
            typer.echo("\nStep 2: Parsing structure...")
            
            # Try each strategy until one passes QA
            for strategy_num, strategy in enumerate(extractor.strategies, 1):
                typer.echo(f"  Trying strategy {strategy_num}...")
                try:
                    document, confidence = strategy.parse(pdf_extractor, standard_id)
                    typer.echo(f"  [OK] Parsed with confidence: {confidence:.2%}")
                    
                    typer.echo(f"\nStep 3: Running QA validation...")
                    qa_result = validator.validate(document, baseline_text)
                    
                    # Track best result (prefer higher QA score, then higher confidence)
                    if best_qa is None or qa_result.score > best_qa.score or (qa_result.score == best_qa.score and confidence > best_confidence):
                        best_confidence = confidence
                        best_document = document
                        best_qa = qa_result
                    
                    # Check if this result passes QA
                    if qa_result.passed:
                        typer.echo(f"[PASS] QA passed! Score: {qa_result.score:.2%}")
                        
                        # Generate output files
                        typer.echo("\nGenerating output files...")
                        json_path = output_gen.generate_main_json(document)
                        qa_path = output_gen.generate_qa_json(qa_result)
                        html_path = output_gen.generate_html_report(document, qa_result, baseline_text)
                        
                        typer.echo(f"[OK] Main JSON: {json_path}")
                        typer.echo(f"[OK] QA JSON: {qa_path}")
                        typer.echo(f"[OK] HTML Report: {html_path}")
                        
                        raise typer.Exit(code=0)
                    else:
                        typer.echo(f"  [FAIL] QA failed. Score: {qa_result.score:.2%} (threshold: {threshold:.2%})")
                        # Try next strategy
                        continue
                
                except Exception as e:
                    typer.echo(f"  [FAIL] Strategy {strategy_num} failed: {e}")
                    continue
    
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit code
        raise
    except Exception as e:
        typer.echo(f"Error during processing: {e}", err=True)
        # Fall through to output best candidate if available
    
    # If we get here, QA failed for all strategies
    if best_document is None:
        typer.echo("\nError: All parsing strategies failed", err=True)
        raise typer.Exit(code=2)
    
    # Output best candidate even if QA failed
    typer.echo(f"\n[WARNING] All strategies failed QA thresholds.")
    typer.echo(f"Outputting best candidate (confidence: {best_confidence:.2%}, QA score: {best_qa.score:.2%})...")
    json_path = output_gen.generate_main_json(best_document)
    qa_path = output_gen.generate_qa_json(best_qa) if best_qa else None
    # Get baseline text for HTML report
    baseline_text_for_report = None
    try:
        with PDFTextExtractor(str(pdf_path)) as pdf_extractor:
            baseline_text_for_report = pdf_extractor.extract_baseline_text()
    except:
        pass
    html_path = output_gen.generate_html_report(best_document, best_qa, baseline_text_for_report)
    
    typer.echo(f"Main JSON: {json_path}")
    if qa_path:
        typer.echo(f"QA JSON: {qa_path}")
    typer.echo(f"HTML Report: {html_path}")
    
    typer.echo("\n[WARNING] QA thresholds not met. Please review the output and adjust parsing if needed.")
    raise typer.Exit(code=1)


@app.command()
def debug(
    pdf_path: str = typer.Argument(..., help="Path to the PDF file"),
    out: str = typer.Option("out", "--out", "-o", help="Output directory"),
    golden: bool = typer.Option(False, "--golden", help="Run in golden mode (stricter QA)"),
):
    """Generate debug artifacts for parsing diagnostics.
    
    This command:
    1. Extracts baseline information (TOC pages, title candidates, paragraph candidates)
    2. Runs the current parser to get detected paragraph IDs
    3. Creates diff artifacts (coverage, missing IDs, extra IDs, first failure)
    4. Outputs baseline.json, detected.json, diff.json, and debug.html
    """
    import json
    import re
    from pathlib import Path
    from pdf2json.baseline import BaselineExtractor
    from pdf2json.debug_diff import create_diff, write_debug_files
    
    # Validate PDF path
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        typer.echo(f"Error: PDF file not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    
    if not pdf_file.suffix.lower() == ".pdf":
        typer.echo(f"Error: Not a PDF file: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    
    # Extract standard ID
    standard_id = extract_standard_id(str(pdf_path))
    typer.echo(f"Debug mode: Processing {standard_id} from {pdf_path}")
    
    # Initialize components
    output_gen = OutputGenerator(out)
    validator = QAValidator(threshold=0.95 if golden else 0.80)
    extractor = Extractor()
    
    try:
        with PDFTextExtractor(str(pdf_path)) as pdf_extractor:
            typer.echo("\nStep 1: Extracting baseline...")
            baseline_extractor = BaselineExtractor(pdf_extractor)
            baseline = baseline_extractor.extract_baseline(standard_id)
            baseline_valid = baseline.get("baseline_valid", False)
            validation_reasons = baseline.get("baseline_validation_reasons", [])
            
            typer.echo(f"[OK] Baseline extracted: {len(baseline['paragraph_candidates'])} paragraph candidates, {len(baseline['toc_pages'])} TOC pages")
            
            # Check baseline validity
            if not baseline_valid:
                typer.echo(f"\n✗ BASELINE_INVALID: Baseline validation failed")
                for reason in validation_reasons:
                    typer.echo(f"  - {reason}")
                
                # Still write files but with invalid baseline
                detected_ids = []  # Empty since we didn't parse
                document = None  # Will need to create empty document or handle None
                # Create a minimal diff with validation reasons
                diff = {
                    "baseline_valid": False,
                    "validation_reasons": validation_reasons,
                    "coverage": None,
                    "baseline_count": len(baseline['paragraph_candidates']),
                    "detected_count": 0,
                    "body_paragraph_count": 0,
                    "missing_ids": [],
                    "extra_ids": [],
                    "first_failure": None,
                    "toc_pages": sorted(list(baseline.get("toc_pages", [])))
                }
                
                # For invalid baseline, we can't write detected.json properly without document
                # So we'll skip that and write what we can
                typer.echo("\nStep 2: Writing debug files (baseline invalid, skipping parser)...")
                output_dir = Path(output_gen.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Write baseline.json
                baseline_path = output_dir / f"{standard_id}.baseline.json"
                with open(baseline_path, 'w', encoding='utf-8') as f:
                    json.dump(baseline, f, ensure_ascii=False, indent=2)
                
                # Write diff.json
                diff_path = output_dir / f"{standard_id}.diff.json"
                with open(diff_path, 'w', encoding='utf-8') as f:
                    json.dump(diff, f, ensure_ascii=False, indent=2)
                
                # Write debug.html (without document, we'll pass None and handle it)
                html_path = output_dir / f"{standard_id}.debug.html"
                from pdf2json.debug_diff import _generate_debug_html
                # Create minimal document for HTML generation
                from pdf2json.models import StandardDocument, StandardTitle, MainContent
                empty_doc = StandardDocument(
                    standard_id=standard_id,
                    standard_title=StandardTitle(hebrew=None, english=None),
                    main=MainContent(sections=[])
                )
                html_content = _generate_debug_html(standard_id, baseline, [], diff, empty_doc)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                typer.echo(f"[OK] Debug files written to {out}/")
                typer.echo("\n⚠ Baseline is invalid. Cannot proceed with parsing/diff. Please fix baseline extraction.")
                raise typer.Exit(code=1)
            
            typer.echo("[OK] Baseline validation passed")
            
            typer.echo("\nStep 2: Running parser...")
            # Run parser using the first strategy
            strategy = extractor.strategies[0]
            document, confidence = strategy.parse(pdf_extractor, standard_id)
            typer.echo(f"[OK] Parsed with confidence: {confidence:.2%}")
            
            # Extract detected paragraph IDs
            detected_ids = _extract_detected_paragraph_ids(document)
            
            typer.echo("\nStep 3: Creating diff...")
            diff = create_diff(baseline, detected_ids, document, standard_id)
            
            if diff.get("baseline_valid"):
                coverage = diff.get("coverage", 0.0)
                typer.echo(f"[OK] Coverage: {coverage:.2%}, Missing: {len(diff.get('missing_ids', []))}, Extra: {len(diff.get('extra_ids', []))}")
            else:
                typer.echo("⚠ Diff creation failed (baseline was invalid)")
            
            # Print summary
            first_missing = diff.get("first_failure")
            first_missing_id = first_missing.get("token") if first_missing else None
            typer.echo(f"\nSummary:")
            typer.echo(f"  baseline_valid: {baseline_valid}")
            typer.echo(f"  baseline_count: {diff.get('baseline_count', 0)}")
            typer.echo(f"  detected_count: {diff.get('detected_count', 0)}")
            if diff.get("baseline_valid"):
                typer.echo(f"  coverage: {diff.get('coverage', 0):.2%}")
            typer.echo(f"  first_missing_id: {first_missing_id or 'None'}")
            typer.echo(f"  toc_pages: {diff.get('toc_pages', [])}")
            
            # Golden mode checks
            golden_failures = []
            if golden and diff.get("baseline_valid"):
                # Check coverage < 0.95
                coverage = diff.get("coverage", 0.0)
                if coverage < 0.95:
                    golden_failures.append(f"Coverage {coverage:.2%} < 0.95")
                
                # Check body paragraphs == 0
                if diff.get("body_paragraph_count", 0) == 0:
                    golden_failures.append("Body paragraphs == 0")
                
                # Check title completeness
                if not document.standard_title or not document.standard_title.hebrew:
                    golden_failures.append("Hebrew title missing")
                elif not re.search(r'\d+', document.standard_title.hebrew):
                    golden_failures.append("Hebrew title missing standard number")
                
                if golden_failures:
                    typer.echo(f"\n⚠ Golden mode FAILURES:")
                    for failure in golden_failures:
                        typer.echo(f"  - {failure}")
            
            typer.echo("\nStep 4: Writing debug files...")
            write_debug_files(output_gen, standard_id, baseline, detected_ids, diff, document)
            typer.echo(f"[OK] Debug files written to {out}/")
            
            # Run QA if golden mode and baseline valid
            if golden and diff.get("baseline_valid"):
                typer.echo("\nStep 5: Running QA validation (golden mode)...")
                baseline_text = pdf_extractor.extract_baseline_text()
                qa_result = validator.validate(document, baseline_text)
                typer.echo(f"[OK] QA Score: {qa_result.score:.2%}")
                if not qa_result.passed:
                    typer.echo(f"⚠ QA failed: {len(qa_result.issues)} issues")
                    for issue in qa_result.issues:
                        typer.echo(f"  - {issue}")
                    if golden_failures:
                        raise typer.Exit(code=1)
            
    except Exception as e:
        typer.echo(f"Error during debug: {e}", err=True)
        import traceback
        traceback.print_exc()
        raise typer.Exit(code=1)


def _extract_detected_paragraph_ids(document) -> List[Dict[str, Any]]:
    """Extract detected paragraph IDs from document.
    
    Returns:
        List of dictionaries with paragraph_id, page (if available), and snippet
    """
    detected = []
    
    # Extract from main content
    for section in document.main.sections:
        for para in section.paragraphs:
            detected.append({
                "paragraph_id": para.paragraph_id,
                "paragraph_id_display": para.paragraph_id_display,
                "snippet": para.content[:80] if para.content else "",
                "source": "main"
            })
        for sub in section.subsections:
            for para in sub.paragraphs:
                detected.append({
                    "paragraph_id": para.paragraph_id,
                    "paragraph_id_display": para.paragraph_id_display,
                    "snippet": para.content[:80] if para.content else "",
                    "source": "main"
                })
    
    # Extract from appendices
    for appendix in [document.appendix_A, document.appendix_B, document.appendix_C]:
        if appendix:
            for section in appendix.sections:
                for para in section.paragraphs:
                    detected.append({
                        "paragraph_id": para.paragraph_id,
                        "paragraph_id_display": para.paragraph_id_display,
                        "snippet": para.content[:80] if para.content else "",
                        "source": f"appendix_{appendix.appendix_id}"
                    })
                for sub in section.subsections:
                    for para in sub.paragraphs:
                        detected.append({
                            "paragraph_id": para.paragraph_id,
                            "paragraph_id_display": para.paragraph_id_display,
                            "snippet": para.content[:80] if para.content else "",
                            "source": f"appendix_{appendix.appendix_id}"
                        })
    
    return detected


@app.command()
def version():
    """Show version information."""
    from pdf2json import __version__
    typer.echo(f"pdf2json version {__version__}")


if __name__ == "__main__":
    app()

