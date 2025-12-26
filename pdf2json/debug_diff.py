"""Diff creation for debug pipeline."""

from typing import List, Dict, Any, Set
from pathlib import Path
import json
from pdf2json.models import StandardDocument
from pdf2json.output import OutputGenerator


def create_diff(baseline: Dict[str, Any], detected_ids: List[Dict[str, Any]], document: StandardDocument, standard_id: str) -> Dict[str, Any]:
    """Create diff between baseline and detected paragraph IDs.
    
    Args:
        baseline: Baseline information from BaselineExtractor (includes baseline_valid)
        detected_ids: List of detected paragraph ID dictionaries
        document: Parsed StandardDocument
        standard_id: Standard ID (e.g., "IAS_16")
        
    Returns:
        Dictionary with coverage, missing_ids, extra_ids, and first_failure (or validation reasons if invalid)
    """
    baseline_valid = baseline.get("baseline_valid", False)
    validation_reasons = baseline.get("baseline_validation_reasons", [])
    
    # If baseline is invalid, return early with validation reasons
    if not baseline_valid:
        return {
            "baseline_valid": False,
            "validation_reasons": validation_reasons,
            "coverage": None,
            "baseline_count": len(baseline.get("paragraph_candidates", [])),
            "detected_count": len(detected_ids),
            "body_paragraph_count": sum(1 for item in detected_ids if item.get("source") == "main"),
            "missing_ids": [],
            "extra_ids": [],
            "first_failure": None,
            "toc_pages": sorted(list(baseline.get("toc_pages", [])))
        }
    
    # Extract baseline paragraph IDs (tokens)
    baseline_tokens: Set[str] = {cand["token"] for cand in baseline["paragraph_candidates"]}
    
    # Extract detected paragraph IDs
    detected_tokens: Set[str] = {item["paragraph_id"] for item in detected_ids}
    
    # Calculate coverage
    baseline_count = len(baseline_tokens)
    detected_count = len(detected_tokens)
    coverage = detected_count / baseline_count if baseline_count > 0 else 0.0
    
    # Find missing IDs (baseline - detected)
    missing_tokens = baseline_tokens - detected_tokens
    missing_ids = []
    for cand in baseline["paragraph_candidates"]:
        if cand["token"] in missing_tokens:
            missing_ids.append({
                "token": cand["token"],
                "token_display": cand.get("token_raw"),
                "page": cand["page"],
                "snippet": cand.get("snippet", ""),
                "pattern": cand.get("regex_name", "unknown")
            })
    
    # Find extra IDs (detected - baseline)
    extra_tokens = detected_tokens - baseline_tokens
    extra_ids = []
    for item in detected_ids:
        if item["paragraph_id"] in extra_tokens:
            extra_ids.append({
                "paragraph_id": item["paragraph_id"],
                "paragraph_id_display": item.get("paragraph_id_display"),
                "snippet": item.get("snippet", ""),
                "source": item.get("source", "")
            })
    
    # Find first failure (first missing ID)
    first_failure = None
    if missing_ids:
        # Sort by page, then by token to find the first one
        sorted_missing = sorted(missing_ids, key=lambda x: (x["page"], x["token"]))
        first_failure = sorted_missing[0]
    
    # Count body paragraphs (exclude appendices)
    body_paragraph_count = sum(
        1 for item in detected_ids
        if item.get("source") == "main"
    )
    
    # Check TOC contamination
    toc_pages = set(baseline["toc_pages"])
    
    return {
        "baseline_valid": True,
        "coverage": coverage,
        "baseline_count": baseline_count,
        "detected_count": detected_count,
        "body_paragraph_count": body_paragraph_count,
        "missing_ids": missing_ids,
        "extra_ids": extra_ids,
        "first_failure": first_failure,
        "toc_pages": sorted(list(toc_pages))
    }


def write_debug_files(output_gen: OutputGenerator, standard_id: str, baseline: Dict[str, Any], 
                      detected_ids: List[Dict[str, Any]], diff: Dict[str, Any], document: StandardDocument):
    """Write debug files to output directory.
    
    Args:
        output_gen: OutputGenerator instance
        standard_id: Standard ID (e.g., "IAS_16")
        baseline: Baseline information
        detected_ids: List of detected paragraph IDs
        diff: Diff information
        document: Parsed StandardDocument
    """
    output_dir = Path(output_gen.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write baseline.json
    baseline_path = output_dir / f"{standard_id}.baseline.json"
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    
    # Write detected.json
    detected_path = output_dir / f"{standard_id}.detected.json"
    
    # Count paragraphs per part
    extracted_counts = {"main": 0, "appendix_A": 0, "appendix_B": 0, "appendix_C": 0}
    for item in detected_ids:
        source = item.get("source", "main")
        if source == "main":
            extracted_counts["main"] += 1
        elif source == "appendix_A":
            extracted_counts["appendix_A"] += 1
        elif source == "appendix_B":
            extracted_counts["appendix_B"] += 1
        elif source == "appendix_C":
            extracted_counts["appendix_C"] += 1
    
    detected_data = {
        "extracted_title_hebrew": document.standard_title.hebrew if document.standard_title else None,
        "extracted_title_english": document.standard_title.english if document.standard_title else None,
        "extracted_paragraph_ids": detected_ids,
        "extracted_counts": extracted_counts,
        "total_count": len(detected_ids),
        "body_count": diff["body_paragraph_count"]
    }
    with open(detected_path, 'w', encoding='utf-8') as f:
        json.dump(detected_data, f, ensure_ascii=False, indent=2)
    
    # Write diff.json
    diff_path = output_dir / f"{standard_id}.diff.json"
    with open(diff_path, 'w', encoding='utf-8') as f:
        json.dump(diff, f, ensure_ascii=False, indent=2)
    
    # Write debug.html
    html_path = output_dir / f"{standard_id}.debug.html"
    html_content = _generate_debug_html(standard_id, baseline, detected_ids, diff, document)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)


def _generate_debug_html(standard_id: str, baseline: Dict[str, Any], detected_ids: List[Dict[str, Any]], 
                         diff: Dict[str, Any], document: StandardDocument) -> str:
    """Generate debug HTML report.
    
    Args:
        standard_id: Standard ID
        baseline: Baseline information
        detected_ids: List of detected paragraph IDs
        diff: Diff information
        document: Parsed StandardDocument
        
    Returns:
        HTML content as string
    """
    baseline_valid = diff.get("baseline_valid", False)
    validation_reasons = diff.get("validation_reasons", [])
    
    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
    <meta charset="UTF-8">
    <title>Debug Report: {standard_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        .metric {{ margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 5px; }}
        .coverage {{ font-size: 24px; font-weight: bold; }}
        .good {{ color: green; }}
        .warning {{ color: orange; }}
        .error {{ color: red; }}
        .invalid {{ background-color: #ffcccc; padding: 15px; border: 2px solid red; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
        th {{ background-color: #4CAF50; color: white; }}
        .missing {{ background-color: #ffcccc; }}
        .extra {{ background-color: #ffffcc; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>Debug Report: {standard_id}</h1>
    
    <h2>Baseline Validation</h2>
"""
    if not baseline_valid:
        html += f"""    <div class="metric invalid">
        <h3 style="color: red; margin-top: 0;">⚠ BASELINE_INVALID</h3>
        <p><strong>Baseline validation failed. Diff results are not reliable.</strong></p>
        <ul>
"""
        for reason in validation_reasons:
            html += f"            <li>{reason}</li>\n"
        html += """        </ul>
    </div>
"""
    else:
        html += """    <div class="metric good">
        <p><strong>✓ Baseline Valid</strong></p>
    </div>
"""
    
    # Only show coverage metrics if baseline is valid
    if baseline_valid:
        html += f"""
    <h2>Coverage Metrics</h2>
    <div class="metric">
        <div class="coverage {'good' if diff.get('coverage', 0) >= 0.95 else 'warning' if diff.get('coverage', 0) >= 0.80 else 'error'}">
            Coverage: {diff.get('coverage', 0):.2%}
        </div>
        <div>Baseline Count: {diff.get('baseline_count', 0)}</div>
        <div>Detected Count: {diff.get('detected_count', 0)}</div>
        <div>Body Paragraphs: {diff.get('body_paragraph_count', 0)}</div>
    </div>
"""
    else:
        html += f"""
    <h2>Baseline Statistics</h2>
    <div class="metric">
        <div>Baseline Count: {diff.get('baseline_count', 0)}</div>
        <div>Detected Count: {diff.get('detected_count', 0)}</div>
        <div>Body Paragraphs: {diff.get('body_paragraph_count', 0)}</div>
        <div style="color: red; font-weight: bold;">Coverage metrics not available due to invalid baseline</div>
    </div>
"""
    
    html += f"""
    <h2>Title Candidates</h2>
    <div class="metric">
        <div><strong>Hebrew:</strong> {baseline['title']['hebrew'] or 'Not found'}</div>
        <div><strong>English:</strong> {baseline['title']['english'] or 'Not found'}</div>
    </div>
"""
    
    html += f"""
    <h2>TOC Pages</h2>
    <div class="metric">
        Pages: {', '.join(map(str, diff.get('toc_pages', []))) if diff.get('toc_pages') else 'None'}
    </div>
"""
    
    # Only show diff details if baseline is valid
    if baseline_valid:
        html += """
    <h2>First Failure</h2>
"""
        if diff.get('first_failure'):
            html += f"""    <div class="metric error">
        <div><strong>Token:</strong> {diff['first_failure']['token']}</div>
        <div><strong>Page:</strong> {diff['first_failure']['page']}</div>
        <div><strong>Snippet:</strong> {diff['first_failure'].get('snippet', '')}</div>
    </div>
"""
        else:
            html += """    <div class="metric good">No failures detected</div>
"""
        
        missing_ids = diff.get('missing_ids', [])
        html += f"""
    <h2>Missing IDs ({len(missing_ids)})</h2>
    <table>
        <tr>
            <th>Token</th>
            <th>Page</th>
            <th>Snippet</th>
            <th>Pattern</th>
        </tr>
"""
        for missing in missing_ids[:50]:  # Show first 50
            html += f"""        <tr class="missing">
            <td>{missing.get('token', '')}</td>
            <td>{missing.get('page', '')}</td>
            <td>{missing.get('snippet', '')}</td>
            <td>{missing.get('pattern', 'unknown')}</td>
        </tr>
"""
        if len(missing_ids) > 50:
            html += f"""        <tr><td colspan="4">... and {len(missing_ids) - 50} more</td></tr>
"""
        
        html += """    </table>
    
"""
        extra_ids = diff.get('extra_ids', [])
        html += f"""    <h2>Extra IDs ({len(extra_ids)})</h2>
    <table>
        <tr>
            <th>Paragraph ID</th>
            <th>Source</th>
            <th>Snippet</th>
        </tr>
"""
        for extra in extra_ids[:50]:  # Show first 50
            html += f"""        <tr class="extra">
            <td>{extra.get('paragraph_id', '')}</td>
            <td>{extra.get('source', '')}</td>
            <td>{extra.get('snippet', '')}</td>
        </tr>
"""
        if len(extra_ids) > 50:
            html += f"""        <tr><td colspan="3">... and {len(extra_ids) - 50} more</td></tr>
"""
        
        html += """    </table>
"""
    
    html += """
</body>
</html>"""
    
    return html

