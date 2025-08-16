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
from datetime import datetime
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
    "issue_date": re.compile(
        r"(?:Revision(?:\s*Date)?|Date\s*of\s*(?:last\s*)?issue|Issued|Issue\s*Date)\s*[:\-]?\s"
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        re.I,
    ),
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

# -------------------------------
# Data model
# -------------------------------
@dataclass
class ParsedSds:
    product_id: int
    vendor: Optional[str]
    product_name: Optional[str]
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

def _split_sections(text: str) -> Tuple[str, str, str, str]:
    """Return sections 1, 2, 14, 16 (empty string if not found)."""
    sections: Dict[str, str] = {}
    # Matches: beginning-of-line optional "Section/SECTION" then number, optional punctuation, then grabs until next section header or EOF.
    sec = re.compile(
        r"(?:^|\n)\s*(?:SECTION|Section)?\s*([0-9]{1,2})[\.:\)]?\s*(.*?)\s*(?=(?:\n\s*(?:SECTION|Section)?\s*[0-9]{1,2}[\.:\)]?)|\Z)",
        re.S,
    )
    for m in sec.finditer(text):
        no = m.group(1).strip()
        body = m.group(2).strip()
        if no not in sections or len(body) > len(sections.get(no, "")):
            sections[no] = body
    return (
        sections.get("1", ""),
        sections.get("2", ""),
        sections.get("14", ""),
        sections.get("16", ""),
    )


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

    sect1, sect2, sect14, sect16 = _split_sections(text)

    vendor = _extract_vendor(sect1)
    product_name = _extract_product_name(sect1, text)

    raw_date = _find(PATTERNS["issue_date"], text) or _find(PATTERNS["issue_date"], sect16)
    issue_date = _normalise_date(raw_date)

    hazard_statements = _extract_hazard_statements(sect2)
    hazardous_substance, haz_conf = _is_hazardous(sect2, hazard_statements)

    dg_flag, dg_class, packing_group, un_number, dg_conf, subsidiary_risks = _dangerous_goods_tuple(sect14)

    return ParsedSds(
        product_id=product_id,
        vendor=vendor,
        product_name=product_name,
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


if __name__ == "__main__":
    _cli()
