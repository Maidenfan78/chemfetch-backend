#!/usr/bin/env python3
"""
Robust SDS parser (rewritten)
- Flexible section detection (handles "SECTION 14:", "Section 14.", and "14. Transport...")
- Negation-aware flags for Dangerous Goods and Hazardous Substance
- Broad date capture + normalization to ISO-8601 (YYYY-MM-DD)
- Vendor / Product name extraction with multiple label variants
- Optional OCR fallback and artifact writes gated by DEBUG_SDS=1
- Multiple entry points: from URL, file path, or bytes
- Emits per-field confidence scores to support QA at scale

Dependencies (soft):
- pdfplumber (primary text extractor)
- PyMuPDF/fitz (optional faster extractor)
- pypdf (optional fallback)
- pytesseract + pdf2image + pillow (optional OCR fallback)

Usage:
  python parse_sds.py --path /path/to/sds.pdf --product-id 123
  python parse_sds.py --url  https://example.com/sds.pdf --product-id 123

Environment:
  DEBUG_SDS=1 -> verbose logging + artifact saving (original_*.pdf, page_*.png)
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

# -------------------------------
# Logging
# -------------------------------
LOG_LEVEL = logging.DEBUG if os.getenv("DEBUG_SDS") == "1" else logging.INFO
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("parse_sds")

# -------------------------------
# Regex patterns
# -------------------------------
PATTERNS: Dict[str, re.Pattern] = {
    # Product / Vendor / Dates
    "product_identifier": re.compile(r"(?:(?:Product\s*(?:name|identifier))|Trade\s*name)\s*[:\-]?\s*(.+)", re.I),
    "product_identifier_alt": re.compile(r"^\s*IDENTIFICATION\s*OF\s*THE\s*SUBSTANCE.*?\n(.*?)\n", re.I | re.S),
    "vendor_block_13": re.compile(r"1\.3\s*(?:Details|Supplier|Manufacturer|Company).*?(?:\n\n|\Z)", re.I | re.S),
    "product_use": re.compile(r"(?:Recommended\s+use|Uses?\s+of\s+the\s+substance(?:/mixture)?|Product\s+use)\s*[:\-]?\s*(.+)", re.I),
    # Dangerous goods / transport
    "dg_none": re.compile(r"(?:not\s+(?:subject|regulated)|not\s+classified\s+as\s+dangerous\s+goods)", re.I),
    "dg_class": re.compile(r"(?:Class|Hazard\s*Class(?:es)?)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9])?)", re.I),
    "packing_group": re.compile(r"(?:Packing\s*Group|PG)\s*[:\-]?\s*(I{1,3}|[1-3])\b", re.I),
    "subsidiary_risks": re.compile(r"Subsidiary\s*Risk(?:s)?\s*[:\-]?\s*([A-Za-z0-9 ,/.-]+)", re.I),
    "un_number": re.compile(r"\bUN(?:/ID)?\s*(?:No\.|Number)?\s*[:\-]?\s*(\d{3,4})\b", re.I),
    # Hazardous / hazard statements (Section 2)
    "haz_none": re.compile(r"(?:not\s+classified\s+as\s+hazardous|non[-\s]?hazardous|does\s+not\s+meet\s+the\s+criteria)", re.I),
    "hazard_statement_line": re.compile(r"\b(H\d{3}[A-Z]?)\b[:\-]?\s*(.+)$", re.I),
}

# SDS section titles and helpers for flexible section numbering
SDS_SECTION_TITLES: Dict[str, str] = {
    "1": "Identification",
    "2": "Hazard Identification",
    "3": "Composition/Information on Ingredients",
    "4": "First-Aid Measures",
    "5": "Fire-Fighting Measures",
    "6": "Accidental Release Measures",
    "7": "Handling and Storage",
    "8": "Exposure Controls/Personal Protection",
    "9": "Physical and Chemical Properties",
    "10": "Stability and Reactivity",
    "11": "Toxicological Information",
    "12": "Ecological Information",
    "13": "Disposal Considerations",
    "14": "Transport Information",
    "15": "Regulatory Information",
    "16": "Other Information",
}

# Allow section numbers written as words ("Section One", "Five.", etc.)
SECTION_WORDS: Dict[str, str] = {
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
}


# --- ISSUE DATE RESOLVER PATCH START -----------------------------------------
# Drop this block into your existing parse_sds.py (e.g., near your regex
# definitions). It adds safer, labeled patterns for SDS issue dates, prioritizes
# Section 16, and avoids matching "Issued by" lines. It expects an existing
# PATTERNS dict and a _normalise_date(str)->str function that returns ISO dates.

_gap = r"(?:[^\d\n]{0,120}?)"  # up to ~120 non-digit chars between label and the date

PATTERNS.update({
    "date_of_issue": re.compile(
        rf"Date\s*of\s*(?:last\s*)?issue{_gap}"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
    "revision_date": re.compile(
        rf"(?:Date\s*of\s*revision|Revision(?:\s*Date)?)({_gap})?"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
    "issue_date_label": re.compile(
        rf"Issue\s*Date{_gap}"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
    "issued_on": re.compile(
        rf"Issued(?!\s*by\b){_gap}"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
    "date_prepared": re.compile(
        rf"Date\s*Prepared{_gap}"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
    "generic_date": re.compile(
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    )
})

def _find_first(pat: re.Pattern, sect16: str, full_text: Optional[str] = None) -> Optional[str]:
    m = pat.search(sect16)
    if m:
        # choose the last capturing group if the pattern has optional groups
        return next((g for g in m.groups()[::-1] if g), None)
    if full_text:
        m = pat.search(full_text)
        if m:
            return next((g for g in m.groups()[::-1] if g), None)
    return None

def _nearest_label_date_anywhere(full_text: str) -> Optional[str]:
    """
    If labeled patterns fail, look for any label token followed by a generic date
    within a short window (catches footer formats or split lines).
    """
    label_tokens = [
        r"Date\s*of\s*issue",
        r"Date\s*of\s*revision",
        r"Issue\s*Date",
        r"Issued(?!\s*by\b)",
        r"Date\s*Prepared",
    ]
    generic = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})"
    for tok in label_tokens:
        m = re.search(rf"{tok}[^\d]{{0,160}}{generic}", full_text, re.I)
        if m:
            # last group is the date
            return m.groups()[-1]
    return None

def _resolve_issue_date(sect16: str, full_text: str) -> Optional[str]:
    """Prefer Section 16, then whole text; enforce sensible label priority.

    Priority: Date of issue -> Revision Date -> Issue Date -> Issued -> Date Prepared
    Includes an optional future-date sanity check (<= 60 days ahead).
    """
    candidates = [
        ("date_of_issue",    _find_first(PATTERNS["date_of_issue"],    sect16, full_text)),
        ("revision_date",    _find_first(PATTERNS["revision_date"],    sect16, full_text)),
        ("issue_date_label", _find_first(PATTERNS["issue_date_label"], sect16, full_text)),
        ("issued_on",        _find_first(PATTERNS["issued_on"],        sect16, full_text)),
        ("date_prepared",    _find_first(PATTERNS["date_prepared"],    sect16, full_text)),
    ]

    for _, raw in candidates:
        if not raw:
            continue
        try:
            iso = _normalise_date(raw)
        except Exception:
            continue
        try:
            dt = datetime.fromisoformat(iso).date()
            if dt <= date.today() + timedelta(days=60):
                return iso
        except Exception:
            # ISO parsing failed unexpectedly—return as-is rather than lose the value
            return iso

    # NEW: nearby generic date after any label token anywhere in the doc
    raw = _nearest_label_date_anywhere(full_text)
    if raw:
        try:
            iso = _normalise_date(raw)
        except Exception:
            iso = raw
        try:
            dt = datetime.fromisoformat(iso).date()
            if dt <= date.today() + timedelta(days=60):
                return iso
        except Exception:
            return iso

    # Fallback: any unlabelled date present in Section 16
    raw = _find_first(PATTERNS["generic_date"], sect16)
    if raw:
        try:
            iso = _normalise_date(raw)
        except Exception:
            iso = raw
        try:
            dt = datetime.fromisoformat(iso).date()
            if dt <= date.today() + timedelta(days=60):
                return iso
        except Exception:
            return iso

    return None
# --- ISSUE DATE RESOLVER PATCH END -------------------------------------------
# =============================================================================
# FIX 2: Enhanced Transport Information Extraction
# Add these new patterns to your PATTERNS dictionary
# =============================================================================

# Add these to your existing PATTERNS dict:
NEW_PATTERNS = {
    "dg_class_enhanced": re.compile(r"(?:Class|Hazard\s*Class(?:es)?|DG\s*Class)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9])?)", re.I),
    "proper_shipping_name": re.compile(r"(?:Proper\s*Shipping\s*Name|PSN)\s*[:\-]?\s*([^,\n]+)", re.I),
    "packing_group_enhanced": re.compile(r"(?:Packing\s*Group|PG|P\.?G\.?)\s*[:\-]?\s*(I{1,3}|[1-3])\b", re.I),
    "signal_word": re.compile(r"(?:Signal\s+word[s]?)\s*[:\-]?\s*(Danger|Warning)", re.I),
    "precautionary_statements": re.compile(r"\b(P\d{3}[A-Z]?)\b[:\-]?\s*([^.]+\.?)", re.I),
    "cas_number": re.compile(r"\b(\d{2,7}-\d{2}-\d)\b"),
    "emergency_phone": re.compile(r"(?:Emergency|24\s*hour|Emergency\s*contact).*?(?:phone|tel|call)\s*[:\-]?\s*([\+\d\s\(\)\-]{10,})", re.I),
}

# Merge new regexes into main PATTERNS
try:
    PATTERNS.update(NEW_PATTERNS)
except Exception:
    pass

# -------------------------------
# Data model
# -------------------------------
@dataclass
class ParsedSds:
    product_id: int
    vendor: Optional[str]
    product_name: Optional[str]
    product_use: Optional[str]
    issue_date: Optional[str]
    hazardous_substance: Optional[bool]
    hazardous_confidence: float
    hazard_statements: List[str]
    dangerous_good: Optional[bool]
    dangerous_goods_confidence: float
    dangerous_goods_class: Optional[str]
    packing_group: Optional[str]
    subsidiary_risks: Optional[str]
    un_number: Optional[str]
    # New: GHS labeling & identifiers
    signal_word: Optional[str]
    precautionary_statements: List[str]
    cas_numbers: List[str]
    proper_shipping_name: Optional[str]
    # Optional: raw section snippets for QA/audits (trimmed)
    section_1_excerpt: Optional[str]
    section_2_excerpt: Optional[str]
    section_14_excerpt: Optional[str]
    section_16_excerpt: Optional[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)
# -------------------------------
# Utilities
# -------------------------------

def _normalise_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y", "%d/%m/%y",
        "%m/%d/%Y", "%m/%d/%y",
        "%d %B %Y", "%d %b %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", raw)
    if m:
        d, M, y = map(int, m.groups())
        if 1 <= d <= 12 and 1 <= M <= 12 and d != M:
            try:
                return datetime.strptime(f"{M}/{d}/{y}", "%m/%d/%Y").date().isoformat()
            except ValueError:
                pass
    return raw  # return as-is if we cannot parse


def _find(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1).strip() if m else None

# -------------------------------
# PDF text extraction
# -------------------------------

def _extract_text_fitz(pdf_bytes: bytes) -> Optional[str]:
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    try:
        text_parts: List[str] = []
        
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text_parts.append(page.get_text("text"))
        text = "\n".join(text_parts)
        logger.debug("PyMuPDF extracted %d chars", len(text))
        return text
    except Exception as e:
        logger.debug("PyMuPDF failed: %s", e)
        return None


def _extract_text_pdfplumber(pdf_bytes: bytes) -> Optional[str]:
    try:
        import pdfplumber
    except Exception:
        return None
    try:
        text_parts: List[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                text_parts.append(txt)
        text = "\n".join(text_parts)
        logger.debug("pdfplumber extracted %d chars", len(text))
        return text
    except Exception as e:
        logger.debug("pdfplumber failed: %s", e)
        return None


def _extract_text_pypdf(pdf_bytes: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return None
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts: List[str] = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        text = "\n".join(text_parts)
        logger.debug("pypdf extracted %d chars", len(text))
        return text
    except Exception as e:
        logger.debug("pypdf failed: %s", e)
        return None


def _ocr_fallback_pages(pdf_bytes: bytes) -> Optional[str]:
    """Very slow. Only used when initial extraction yields too little text.
    Requires: pdf2image, pytesseract, pillow, and system poppler/gs.
    """
    if os.getenv("DEBUG_SDS") != "1":  # gate behind debug, to avoid prod slowness
        return None
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image
        import pytesseract
    except Exception as e:
        logger.debug("OCR deps missing: %s", e)
        return None
    try:
        pages = convert_from_bytes(pdf_bytes, dpi=300)
        ocr_texts: List[str] = []
        for idx, img in enumerate(pages, start=1):
            if os.getenv("DEBUG_SDS") == "1":
                img.save(f"page_{idx}_debug.png")
            ocr_texts.append(pytesseract.image_to_string(img))
        text = "\n".join(ocr_texts)
        logger.debug("OCR extracted %d chars", len(text))
        return text
    except Exception as e:
        logger.debug("OCR failed: %s", e)
        return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Try multiple extractors; last resort OCR in debug."""
    for extractor in (_extract_text_fitz, _extract_text_pdfplumber, _extract_text_pypdf):
        text = extractor(pdf_bytes)
        if text and len(text) >= 800:  # good enough
            return text
    # If we got some text but small, still return it; else try OCR (debug only)
    for extractor in (_extract_text_fitz, _extract_text_pdfplumber, _extract_text_pypdf):
        text = extractor(pdf_bytes)
        if text and len(text) > 0:
            if len(text) < 800:
                ocr_text = _ocr_fallback_pages(pdf_bytes)
                return ocr_text or text
            return text
    # nothing, attempt OCR
    ocr_text = _ocr_fallback_pages(pdf_bytes)
    return ocr_text or ""

# -------------------------------
# Section splitting & field extraction
# -------------------------------

def _split_sections(text: str) -> Dict[str, str]:
    """Split the full text into a mapping of section number -> body.

    Handles headings like "Section 1", "1.", "One -" etc. Returns the longest
    body found for each section number.
    """
    sections: Dict[str, str] = {}
    word_pat = "|".join(SECTION_WORDS.keys())
    sec = re.compile(
        rf"(?:^|\n)\s*(?:SECTION|Section)?\s*(?:(?P<num>\d{{1,2}})|(?P<word>{word_pat}))[\.:\)]?\s*(?P<body>.*?)\s*(?=(?:\n\s*(?:SECTION|Section)?\s*(?:\d{{1,2}}|{word_pat})[\.:\)]?)|\Z)",
        re.I | re.S,
    )
    for m in sec.finditer(text):
        num = m.group("num")
        if not num:
            num = SECTION_WORDS.get(m.group("word").lower())
        body = m.group("body").strip()
        if num and (num not in sections or len(body) > len(sections[num])):
            sections[num] = body
    return sections


def _trim_excerpt(s: str, max_len: int = 900) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len]


def _extract_vendor(sect1: str) -> Optional[str]:
    # Try explicit 1.3 block first
    m = PATTERNS["vendor_block_13"].search(sect1)
    if m:
        block = m.group(0)
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        for ln in lines:
            if re.search(r"^(?:Supplier|Company|Manufacturer|Distributor)\b", ln, re.I):
                # Inline value after ':'
                m2 = re.match(r"^(?:Supplier|Company|Manufacturer|Distributor)\s*[:\-]?\s*(.+)$", ln, re.I)
                if m2:
                    cand = m2.group(1).strip()
                    if cand and not re.search(r"(Address|Street|Road|Drive|Avenue|Tel|Phone|Email|Website|Emergency)", cand, re.I):
                        return cand
        # If label is alone on a line, try next non-contact line
        for i, ln in enumerate(lines):
            if re.match(r"^(?:Supplier|Company|Manufacturer|Distributor)\s*[:\-]?\s*$", ln, re.I):
                for j in range(i + 1, min(i + 6, len(lines))):
                    cand = lines[j]
                    if cand and not re.search(r"(Address|Street|Road|Drive|Avenue|Tel|Phone|Email|Website|Emergency)", cand, re.I):
                        if len(cand.split()) >= 2 and not re.search(r"\d{2,}", cand):
                            return cand
    # Fallback: scan entire section 1 for labeled lines
    for ln in [l.strip() for l in sect1.splitlines() if l.strip()]:
        m3 = re.match(r"^(Supplier|Company|Manufacturer|Distributor)\s*[:\-]?\s*(.+)$", ln, re.I)
        if m3:
            cand = m3.group(2).strip()
            if cand and not re.search(r"(Address|Street|Road|Drive|Avenue|Tel|Phone|Email|Website|Emergency)", cand, re.I):
                return cand
    return None


def _extract_product_name(sect1: str, text: str) -> Optional[str]:
    # 1) Labeled product identifier/name inside Section 1
    m = PATTERNS["product_identifier"].search(sect1)
    if m:
        return m.group(1).strip()
    # 2) Try unlabeled first line after section header as a title-like line
    if sect1:
        first_line = (sect1.splitlines() or [""])[0].strip()
        if 2 <= len(first_line.split()) <= 12 and not re.search(r"(safety\s+data\s+sheet|revision|version)", first_line, re.I):
            return first_line
    # 3) Global scan as last resort
    m2 = PATTERNS["product_identifier"].search(text)
    if m2:
        return m2.group(1).strip()
    return None


def _extract_product_use(sect1: str) -> Optional[str]:
    """Grab recommended use / product use from Section 1."""
    m = PATTERNS["product_use"].search(sect1)
    if m:
        return m.group(1).strip()
    return None


def _extract_hazard_statements(sect2: str) -> List[str]:
    hazards: List[str] = []
    for ln in sect2.splitlines():
        ln = ln.strip()
        m = PATTERNS["hazard_statement_line"].search(ln)
        if m:
            code = m.group(1).upper()
            desc = m.group(2).strip()
            hazards.append(f"{code} {desc}")
    # Some SDS list statements under a header without codes
    if not hazards:
        lines = sect2.splitlines()
        capture = False
        for ln in lines:
            if re.search(r"Hazard\s*Statements?", ln, re.I):
                capture = True
                continue
            if capture:
                if not ln.strip():
                    break
                hazards.append(ln.strip())
    return hazards


def _dangerous_goods_tuple(sect14: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str], float, Optional[str]]:
    """Return (is_dg, class, pg, un, confidence, subsidiary_risks)."""
    if not sect14.strip():
        return False, None, None, None, 0.0, None
    s14 = sect14
    if PATTERNS["dg_none"].search(s14):
        return False, None, None, None, 1.0, None
    un = _find(PATTERNS["un_number"], s14)
    dg_class = _find(PATTERNS["dg_class"], s14)
    pg = _find(PATTERNS["packing_group"], s14)
    subs = _find(PATTERNS["subsidiary_risks"], s14)
    is_dg = bool(un or dg_class or pg)
    conf = 0.0
    if is_dg:
        # Confidence heuristic: explicit UN + class -> 1.0, any single signal -> 0.6
        conf = 1.0 if (un and dg_class) else 0.8 if (un or dg_class) and pg else 0.6
    return is_dg, dg_class, pg, un, conf, subs


def _is_hazardous(sect2: str, hazard_statements: List[str]) -> Tuple[bool, float]:
    s2 = sect2.lower()
    if PATTERNS["haz_none"].search(s2):
        return False, 1.0
    if hazard_statements:
        return True, 0.9
    # fallback textual hints
    if re.search(r"\bhazard(?:ous|s)\b", s2):
        return True, 0.5
    return False, 0.2

# =============================================================================
# FIX 1: Enhanced Vendor Extraction
# Replace your existing _extract_vendor function with this improved version
# =============================================================================

def _extract_vendor_improved(sect1: str, sect16: str, full_text: str) -> Optional[str]:
    """Enhanced vendor extraction that checks Section 16 first."""
    # Priority 1: Check Section 16 for "Prepared by" statements
    if sect16:
        prep_patterns = [
            re.compile(r"(?:SDS\s+)?(?:Prepared|Issued)\s+by\s*[:\-]?\s*([^,\n]+)", re.I),
            re.compile(r"Prepared\s*[:\-]?\s*([^,\n]+)", re.I),
        ]
        for pattern in prep_patterns:
            m = pattern.search(sect16)
            if m:
                vendor = m.group(1).strip()
                # Filter out non-vendor text
                if vendor and not re.search(r"(Address|Street|Road|Tel|Phone|Email|Website|Emergency|Date)", vendor, re.I):
                    if len(vendor.split()) >= 2:  # Company names typically have 2+ words
                        return vendor

    # Priority 2: Standard vendor patterns in Section 1
    vendor_patterns = [
        re.compile(r"(?:Supplier|Company|Manufacturer|Distributor)\s*[:\-]?\s*([^,\n]+)", re.I),
    ]
    for text_section in [sect1, full_text]:
        for pattern in vendor_patterns:
            m = pattern.search(text_section or "")
            if m:
                vendor = m.group(1).strip()
                if vendor and not re.search(r"(Address|Street|Road|Tel|Phone|Email|Website|Emergency)", vendor, re.I):
                    if len(vendor.split()) >= 2:
                        return vendor

    # Priority 3: Try explicit 1.3 block (existing logic)
    m = re.search(r"1\.3\s*(?:Details|Supplier|Manufacturer|Company).*?(?:\n\n|\Z)", sect1 or "", re.I | re.S)
    if m:
        block = m.group(0)
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if re.search(r"^(?:Supplier|Company|Manufacturer|Distributor)\b", ln, re.I):
                m2 = re.match(r"^(?:Supplier|Company|Manufacturer|Distributor)\s*[:\-]?\s*(.+)$", ln, re.I)
                if m2:
                    cand = m2.group(1).strip()
                    if cand and not re.search(r"(Address|Street|Road|Tel|Phone|Email|Website|Emergency)", cand, re.I):
                        return cand
                # Check next line
                if i + 1 < len(lines):
                    cand = lines[i + 1]
                    if cand and len(cand.split()) >= 2:
                        return cand
    return None

# =============================================================================
# FIX 3: Add Signal Word and P-Code Extraction 
# Add these new functions to extract GHS labeling information
# =============================================================================

def _extract_signal_word(sect2: str) -> Optional[str]:
    """Extract GHS signal word (Danger or Warning)."""
    m = NEW_PATTERNS["signal_word"].search(sect2 or "")
    return m.group(1) if m else None

def _extract_precautionary_statements(sect2: str) -> List[str]:
    """Extract P-codes and their descriptions."""
    statements: List[str] = []
    for m in NEW_PATTERNS["precautionary_statements"].finditer(sect2 or ""):
        code = m.group(1).upper()
        desc = m.group(2).strip().rstrip('.')
        statements.append(f"{code} {desc}")
    return statements

def _extract_cas_numbers(text: str) -> List[str]:
    """Extract all CAS numbers from the full text."""
    cas_numbers: List[str] = []
    for m in NEW_PATTERNS["cas_number"].finditer(text or ""):
        cas = m.group(1)
        if cas not in cas_numbers:
            cas_numbers.append(cas)
    return cas_numbers

def _extract_proper_shipping_name(sect14: str) -> Optional[str]:
    """Extract proper shipping name from transport section."""
    m = NEW_PATTERNS["proper_shipping_name"].search(sect14 or "")
    if m:
        return m.group(1).strip()
    # Fallback: look for shipping name patterns without explicit label
    lines = (sect14 or "").splitlines()
    for line in lines:
        if "ALCOHOL" in line.upper() and ("N.O.S" in line.upper() or "NOS" in line.upper()):
            # Extract the shipping name part
            clean_line = re.sub(r"UN\d{4}\s*", "", line).strip()
            if len(clean_line) > 5:
                return clean_line
    return None

def _dangerous_goods_tuple_improved(sect14: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str], float, Optional[str]]:
    """Enhanced transport information extraction."""
    if not (sect14 or "").strip():
        return False, None, None, None, 0.0, None
    s14 = sect14
    # Check for "not regulated" first
    if re.search(r"(?:not\s+(?:subject|regulated)|not\s+classified\s+as\s+dangerous\s+goods)", s14, re.I):
        return False, None, None, None, 1.0, None
    # Extract transport details using enhanced patterns
    un = None
    m = re.search(r"\b(?:UN|UN/ID)\s*(?:No\.?|Number)?\s*[:\-]?\s*(\d{3,4})\b", s14, re.I)
    if m:
        un = m.group(1)
    dg_class = None
    m = NEW_PATTERNS["dg_class_enhanced"].search(s14)
    if m:
        dg_class = m.group(1)
    pg = None
    m = NEW_PATTERNS["packing_group_enhanced"].search(s14)
    if m:
        pg = m.group(1)
    subs = None
    m = re.search(r"(?:Subsidiary\s*Risk(?:s)?|Sub\s*Risk)\s*[:\-]?\s*([A-Za-z0-9 ,/.-]+)", s14, re.I)
    if m:
        subs = m.group(1)
    # Determine if dangerous good
    is_dg = bool(un or dg_class or pg)
    # Calculate confidence - improved scoring
    conf = 0.0
    if is_dg:
        signals = sum(1 for x in [un, dg_class, pg] if x)
        if un and dg_class:
            conf = 1.0  # Both UN and class = very confident
        elif signals >= 2:
            conf = 0.8  # Any two signals = confident
        else:
            conf = 0.6  # One signal = moderately confident
    return is_dg, dg_class, pg, un, conf, subs

# -------------------------------
# Core parse
# -------------------------------

def _parse_core(pdf_bytes: bytes, *, product_id: int) -> ParsedSds:
    if os.getenv("DEBUG_SDS") == "1":
        with open(f"original_{product_id}.pdf", "wb") as f:
            f.write(pdf_bytes)
    text = extract_text_from_pdf(pdf_bytes)
    if not text:
        logger.warning("No text extracted from PDF")
    # Normalise whitespace a bit
    text = text.replace("\x00", " ")

    sections = _split_sections(text)
    sect1 = sections.get("1", "")
    sect2 = sections.get("2", "")
    sect14 = sections.get("14", "")
    sect16 = sections.get("16", "")

    vendor = _extract_vendor_improved(sect1, sect16, text)
    product_name = _extract_product_name(sect1, text)
    product_use = _extract_product_use(sect1)

    issue_date = _resolve_issue_date(sect16, text)

    hazard_statements = _extract_hazard_statements(sect2)
    hazardous_substance, haz_conf = _is_hazardous(sect2, hazard_statements)
    signal_word = _extract_signal_word(sect2)
    precautionary_statements = _extract_precautionary_statements(sect2)
    cas_numbers = _extract_cas_numbers(text)
    proper_shipping_name = _extract_proper_shipping_name(sect14)

    dg_flag, dg_class, packing_group, un_number, dg_conf, subsidiary_risks = _dangerous_goods_tuple_improved(sect14)

    return ParsedSds(
        product_id=product_id,
        vendor=vendor,
        product_name=product_name,
        product_use=product_use,
        issue_date=issue_date,
        hazardous_substance=hazardous_substance,
        hazardous_confidence=haz_conf,
        hazard_statements=hazard_statements,
        dangerous_good=dg_flag,
        dangerous_goods_confidence=dg_conf,
        dangerous_goods_class=dg_class,
        packing_group=packing_group,
        subsidiary_risks=subsidiary_risks,
        un_number=un_number,
        signal_word=signal_word,
        precautionary_statements=precautionary_statements,
        cas_numbers=cas_numbers,
        proper_shipping_name=proper_shipping_name,
        section_1_excerpt=_trim_excerpt(sect1) if sect1 else None,
        section_2_excerpt=_trim_excerpt(sect2) if sect2 else None,
        section_14_excerpt=_trim_excerpt(sect14) if sect14 else None,
        section_16_excerpt=_trim_excerpt(sect16) if sect16 else None,
    )

# -------------------------------
# Public entry points
# -------------------------------

def parse_sds_bytes(data: bytes, *, product_id: int) -> ParsedSds:
    return _parse_core(data, product_id=product_id)


def parse_sds_path(path: str, *, product_id: int) -> ParsedSds:
    with open(path, "rb") as f:
        data = f.read()
    return _parse_core(data, product_id=product_id)


def parse_sds_pdf(url: str, *, product_id: int) -> ParsedSds:
    import requests
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return _parse_core(resp.content, product_id=product_id)

# -------------------------------
# CLI
# -------------------------------

def _cli() -> None:
    ap = argparse.ArgumentParser(description="Parse SDS PDF into structured JSON")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--path", type=str, help="Path to local PDF")
    src.add_argument("--url", type=str, help="URL to remote PDF")
    ap.add_argument("--product-id", type=int, required=True, help="Internal product id")
    ap.add_argument("--out", type=str, help="Write JSON to this path (else print)")
    args = ap.parse_args()

    try:
        if args.path:
            parsed = parse_sds_path(args.path, product_id=args.product_id)
        else:
            parsed = parse_sds_pdf(args.url, product_id=args.product_id)

        payload = parsed.to_json()
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(payload)
            logger.info("Wrote %s", args.out)
        else:
            print(payload)
    except Exception as e:
        error_response = {
            "error": str(e),
            "product_id": args.product_id
        }
        print(json.dumps(error_response))
        exit(1)


if __name__ == "__main__":
    _cli()
