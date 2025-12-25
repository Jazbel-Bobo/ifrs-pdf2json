"""CLI commands using Typer."""

import sys
from pathlib import Path
from typing import Optional
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
            typer.echo(f"✓ Extracted {len(baseline_text)} characters")
            
            # Step 2 & 3: Try parsing strategies in loop until QA passes
            typer.echo("\nStep 2: Parsing structure...")
            
            # Try each strategy until one passes QA
            for strategy_num, strategy in enumerate(extractor.strategies, 1):
                typer.echo(f"  Trying strategy {strategy_num}...")
                try:
                    document, confidence = strategy.parse(pdf_extractor, standard_id)
                    typer.echo(f"  ✓ Parsed with confidence: {confidence:.2%}")
                    
                    typer.echo(f"\nStep 3: Running QA validation...")
                    qa_result = validator.validate(document, baseline_text)
                    
                    # Track best result (prefer higher QA score, then higher confidence)
                    if best_qa is None or qa_result.score > best_qa.score or (qa_result.score == best_qa.score and confidence > best_confidence):
                        best_confidence = confidence
                        best_document = document
                        best_qa = qa_result
                    
                    # Check if this result passes QA
                    if qa_result.passed:
                        typer.echo(f"✓ QA passed! Score: {qa_result.score:.2%}")
                        
                        # Generate output files
                        typer.echo("\nGenerating output files...")
                        json_path = output_gen.generate_main_json(document)
                        qa_path = output_gen.generate_qa_json(qa_result)
                        html_path = output_gen.generate_html_report(document, qa_result, baseline_text)
                        
                        typer.echo(f"✓ Main JSON: {json_path}")
                        typer.echo(f"✓ QA JSON: {qa_path}")
                        typer.echo(f"✓ HTML Report: {html_path}")
                        
                        raise typer.Exit(code=0)
                    else:
                        typer.echo(f"  ✗ QA failed. Score: {qa_result.score:.2%} (threshold: {threshold:.2%})")
                        # Try next strategy
                        continue
                
                except Exception as e:
                    typer.echo(f"  ✗ Strategy {strategy_num} failed: {e}")
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
    typer.echo(f"\n⚠ All strategies failed QA thresholds.")
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
    
    typer.echo("\n⚠ QA thresholds not met. Please review the output and adjust parsing if needed.")
    raise typer.Exit(code=1)


@app.command()
def version():
    """Show version information."""
    from pdf2json import __version__
    typer.echo(f"pdf2json version {__version__}")


if __name__ == "__main__":
    app()

