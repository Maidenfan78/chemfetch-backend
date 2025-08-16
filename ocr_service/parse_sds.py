from __future__ import annotations

import json
import logging
import re
import pytesseract
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from PIL import Image
from typing import Any, Dict, List, Optional, Tuple

import requests
import pdfplumber

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# ---------------------------------------------------------------------------
# Regex patterns for key fields
# ---------------------------------------------------------------------------
PATTERNS: Dict[str, re.Pattern] = {
    "issue_date": re.compile(
        r"(?:Revision|Revised|Date)\s*:\s*(\d{4}-\d{2}-\d{2})", 
        re.I
    ),
    "dg_class": re.compile(
        r"\b(?:Class|Classification)\s*[:\-]?\s*(\d+\.?\d*)", 
        re.I
    ),
    "packing_group": re.compile(
        r"\bPacking\s+Group\s*[:\-]?\s*([IVX]+)", 
        re.I
    ),
    "subsidiary_risks": re.compile(
        r"\bSubsidiary\s+Risk(?:s)?\s*[:\-]?\s*([0-9A-Z\., ]+)", 
        re.I
    ),
    "vendor": re.compile(
        r"1\.3\s+Details\s+of\s+the\s+supplier\s+of\s+the\s+safety\s+data\s+sheet\s+([^\n]+)", 
        re.I
    ),
}

ISO_IN: Tuple[str, ...] = ("%d %B %Y", "%d/%m/%Y", "%Y-%m-%d")

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _split_sections(text: str) -> Tuple[str, str, str, str]:
    # More robust section splitting that handles OCR errors
    sections = {}
    section_pattern = re.compile(r"SECTION\s+(\d+)\s*:\s*(.*?)(?=SECTION\s+\d+|$)", re.I | re.DOTALL)
    
    for match in section_pattern.finditer(text):
        section_num = match.group(1).strip()
        section_content = match.group(2).strip()
        sections[section_num] = section_content
    
    logger.debug(f"Split sections: Found sections: {list(sections.keys())}")
    return (
        sections.get("1", ""),
        sections.get("2", ""),
        sections.get("14", ""),
        sections.get("16", ""),
    )


def _find(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    if m:
        result = m.group(1).strip()
        logger.debug(f"Pattern '{pattern.pattern}' found: '{result}'")
        return result
    else:
        logger.debug(f"Pattern '{pattern.pattern}' not found")
        return None


def _normalise_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    for fmt in ISO_IN:
        try:
            result = datetime.strptime(raw, fmt).date().isoformat()
            logger.debug(f"Date normalized: '{raw}' -> '{result}'")
            return result
        except ValueError:
            continue
    logger.debug(f"Date format not recognized: '{raw}'")
    return raw


def _extract_vendor(sect1: str) -> Optional[str]:
    # First try the vendor pattern
    vendor_match = PATTERNS["vendor"].search(sect1)
    if vendor_match:
        vendor = vendor_match.group(1).strip()
        # Clean up vendor name - remove address lines
        vendor_lines = vendor.split('\n')
        for line in vendor_lines:
            if line.strip() and not re.search(r"\b(Address|Telephone|Street|Drive|Avenue|Road|Emergency|Facsimile)\b", line, re.I):
                return line.strip()
    
    # Fallback to line-by-line search
    lines = [l.strip() for l in sect1.splitlines() if l.strip()]
    logger.debug(f"Section 1 lines: {lines[:10]}...")
    
    # Look for manufacturer/supplier keywords
    for i, line in enumerate(lines):
        if re.search(r"^(Manufacturer|Supplier)\b", line, re.I):
            # Try to extract vendor name from the same line
            # Handle formats: "Manufacturer Nicepak Products" and "Manufacturer: Nicepak Products"
            parts = re.split(r"Manufacturer|Supplier|[:]", line, maxsplit=1, flags=re.I)
            if len(parts) > 1:
                candidate = parts[1].strip()
                if candidate and len(candidate.split()) >= 2:
                    logger.debug(f"Vendor found (inline): '{candidate}'")
                    return candidate
            
            # Look at next lines for vendor name
            for j in range(i+1, min(len(lines), i+4)):
                candidate = lines[j]
                # Skip lines that are clearly not vendor names
                if not re.search(r"\b(Address|Telephone|Street|Drive|Avenue|Road|Emergency|Facsimile|Vic|NSW|QLD|WA|SA|TAS|NT|ACT)\b", candidate, re.I):
                    if candidate and len(candidate.split()) >= 2:
                        logger.debug(f"Vendor found (next line): '{candidate}'")
                        return candidate
    
    logger.debug("Vendor not found in section 1")
    return None


def _extract_hazard_statements(sect2: str) -> List[str]:
    # More flexible hazard statement detection
    statements = []
    # Look for H-codes anywhere in the line
    for line in sect2.splitlines():
        line = line.strip()
        if re.search(r"\bH\d{3}\b", line):
            statements.append(line)
    
    # Also look for classification statements
    if not statements and "does not meet the criteria for classification" in sect2.lower():
        statements.append("No hazard classification")
    
    logger.debug(f"Found {len(statements)} hazard statements")
    return statements


def _has_dangerous_goods(sect14: str, dg_class: Optional[str], packing_group: Optional[str]) -> bool:
    # Check for explicit dangerous goods mentions
    dangerous_phrases = [
        r"dangerous\s+goods",
        r"hazard\s+class",
        r"un\s+number",
        r"packing\s+group"
    ]
    
    for phrase in dangerous_phrases:
        if re.search(phrase, sect14, re.I):
            return True
    
    # Check if class or packing group was found
    return bool(dg_class or packing_group)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ParsedSds:
    product_id: int
    vendor: Optional[str]
    issue_date: Optional[str]
    hazardous_substance: bool
    dangerous_good: bool
    dangerous_goods_class: Optional[str]
    packing_group: Optional[str]
    subsidiary_risks: Optional[str]
    hazard_statements: List[str]
    raw_json: Dict[str, Any]

    def as_upsert_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("product_id")
        return d

# ---------------------------------------------------------------------------
# Main parsing function
# ---------------------------------------------------------------------------

def parse_sds_pdf(url: str, *, product_id: int) -> ParsedSds:
    """Download a PDF SDS and return parsed fields, with OCR fallback for image-only documents."""
    logger.info("Fetching SDS PDF → %s", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    pdf_bytes = BytesIO(resp.content)
    
    # Save original PDF for debugging
    with open(f"original_{product_id}.pdf", "wb") as f:
        f.write(pdf_bytes.getbuffer())
    logger.info("Saved original PDF for debugging")

    text = ""
    used_ocr = False
    try:
        # First try with pdfplumber text extraction
        with pdfplumber.open(pdf_bytes) as pdf:
            pages = pdf.pages
            texts = [p.extract_text() or "" for p in pages]
            text = "\n".join(texts)
            if any(t.strip() for t in texts):
                logger.info("Extracted text with pdfplumber")
                logger.debug(f"First 500 characters: {text[:500]}")
                pdf_bytes.seek(0)  # Reset buffer position
            else:
                logger.info("No text extracted with pdfplumber")
                used_ocr = True
    except Exception as e:
        logger.error("pdfplumber failed: %s", str(e))
        used_ocr = True
        text = ""

    # If no text found, use Tesseract OCR with pdfplumber images
    if used_ocr:
        logger.info("Performing Tesseract OCR")
        ocr_lines = []
        try:
            with pdfplumber.open(pdf_bytes) as pdf:
                for i, page in enumerate(pdf.pages):
                    try:
                        # Get image from pdfplumber
                        img = page.to_image(resolution=300).original
                        # Preprocess image for better OCR
                        img = img.convert('L')  # Grayscale
                        
                        # Save image for debugging
                        img.save(f"page_{i+1}_{product_id}.png")
                        logger.info(f"Saved page {i+1} image for debugging")
                        
                        # Use Tesseract with custom configuration
                        page_text = pytesseract.image_to_string(
                            img, 
                            config='--psm 6 -c preserve_interword_spaces=1'
                        )
                        ocr_lines.append(page_text)
                        logger.info("OCR page %d completed: %d characters", i+1, len(page_text))
                        logger.debug(f"First 200 characters: {page_text[:200]}")
                    except Exception as e:
                        logger.error("Error during OCR on page %d: %s", i+1, str(e))
            text = "\n".join(ocr_lines)
            
            # Save full OCR text for debugging
            with open(f"ocr_text_{product_id}.txt", "w", encoding="utf-8") as f:
                f.write(text)
            logger.info("Saved full OCR text for debugging")
        except Exception as e:
            logger.error("PDF processing failed: %s", str(e))
            text = ""

    logger.info(f"Total text length: {len(text)} characters")
    
    sect1, sect2, sect14, sect16 = _split_sections(text)
    logger.info(f"Section 1 length: {len(sect1)}")
    logger.info(f"Section 2 length: {len(sect2)}")
    logger.info(f"Section 14 length: {len(sect14)}")
    logger.info(f"Section 16 length: {len(sect16)}")
    
    # Extract fields with improved patterns
    vendor = _extract_vendor(sect1)
    raw_date = _find(PATTERNS["issue_date"], text) or _find(PATTERNS["issue_date"], sect16)
    issue_date = _normalise_date(raw_date)
    dg_class = _find(PATTERNS["dg_class"], sect14)
    packing_group = _find(PATTERNS["packing_group"], sect14)
    subsidiary_risks = _find(PATTERNS["subsidiary_risks"], sect14)
    hazard_statements = _extract_hazard_statements(sect2)
    dangerous_good = _has_dangerous_goods(sect14, dg_class, packing_group)
    hazardous_substance = bool(hazard_statements) or "hazardous" in sect2.lower()

    parsed = {
        "vendor": vendor,
        "issue_date": issue_date,
        "hazardous_substance": hazardous_substance,
        "dangerous_good": dangerous_good,
        "dangerous_goods_class": dg_class,
        "packing_group": packing_group,
        "subsidiary_risks": subsidiary_risks,
        "hazard_statements": hazard_statements,
    }

    logger.info("Parsed results:")
    for k, v in parsed.items():
        logger.info(f"  {k}: {v}")

    return ParsedSds(
        product_id=product_id,
        raw_json=json.loads(json.dumps(parsed)),
        **parsed
    )

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python ocr_service/parse_sds.py <PRODUCT_ID> <PDF_URL>")
        sys.exit(1)

    try:
        res = parse_sds_pdf(sys.argv[2], product_id=int(sys.argv[1]))
        # Output JSON for the Node.js backend to parse
        print(json.dumps(res.as_upsert_dict()))
    except Exception as e:
        logger.error(f"Error parsing SDS: {str(e)}")
        # Output error in JSON format
        print(json.dumps({"error": str(e)}))
        sys.exit(1)