#!/usr/bin/env python3
"""
Quick fixes for the existing parse_sds.py to address immediate issues

This file shows the specific changes to make to your current parser
to fix the null values and add the most important missing information.

Usage: Apply these changes to your existing parse_sds.py
"""

import re
from typing import Optional, List, Dict, Tuple

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
            m = pattern.search(text_section)
            if m:
                vendor = m.group(1).strip()
                if vendor and not re.search(r"(Address|Street|Road|Tel|Phone|Email|Website|Emergency)", vendor, re.I):
                    if len(vendor.split()) >= 2:
                        return vendor
    
    # Priority 3: Try explicit 1.3 block (existing logic)
    m = re.search(r"1\.3\s*(?:Details|Supplier|Manufacturer|Company).*?(?:\n\n|\Z)", sect1, re.I | re.S)
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

def _dangerous_goods_tuple_improved(sect14: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str], float, Optional[str]]:
    """Enhanced transport information extraction."""
    if not sect14.strip():
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

# =============================================================================
# FIX 3: Add Signal Word and P-Code Extraction 
# Add these new functions to extract GHS labeling information
# =============================================================================

def _extract_signal_word(sect2: str) -> Optional[str]:
    """Extract GHS signal word (Danger or Warning)."""
    m = NEW_PATTERNS["signal_word"].search(sect2)
    return m.group(1) if m else None

def _extract_precautionary_statements(sect2: str) -> List[str]:
    """Extract P-codes and their descriptions."""
    statements = []
    for m in NEW_PATTERNS["precautionary_statements"].finditer(sect2):
        code = m.group(1).upper()
        desc = m.group(2).strip().rstrip('.')
        statements.append(f"{code} {desc}")
    return statements

def _extract_cas_numbers(text: str) -> List[str]:
    """Extract all CAS numbers from the full text."""
    cas_numbers = []
    for m in NEW_PATTERNS["cas_number"].finditer(text):
        cas = m.group(1)
        if cas not in cas_numbers:
            cas_numbers.append(cas)
    return cas_numbers

def _extract_proper_shipping_name(sect14: str) -> Optional[str]:
    """Extract proper shipping name from transport section."""
    m = NEW_PATTERNS["proper_shipping_name"].search(sect14)
    if m:
        return m.group(1).strip()
    
    # Fallback: look for shipping name patterns without explicit label
    lines = sect14.splitlines()
    for line in lines:
        if "ALCOHOL" in line.upper() and ("N.O.S" in line.upper() or "NOS" in line.upper()):
            # Extract the shipping name part
            clean_line = re.sub(r"UN\d{4}\s*", "", line).strip()
            if len(clean_line) > 5:
                return clean_line
    
    return None

# =============================================================================
# QUICK TEST FUNCTION
# Run this to test your improvements
# =============================================================================

def test_improvements():
    """Test the improvements with sample text from your result."""
    
    # Sample text from your result-174.json
    sect16_sample = "OTHER INFORMATION SDS Prepared by Nicepak Products Pty Ltd Date Prepared"
    sect2_sample = """HAZARDS IDENFICATION Description Contains Isopropyl Alcohol 64% which is hazardous according to Worksafe Australia. GHS label elements Signal Words Danger Hazard Classification Highly flammable liquid and vapour - category 2 Eye irritation - category 2A Specific target organ toxicity (single exposure) – category 3 Hazard Statement(s) H225 Highly flammable liquid and vapour. H319 Causes serious eye irritation. H336 May cause drowsiness or dizziness. Precautionary Statement(s) P101 If medical advice is needed, have product container or label at hand. P102 Keep out of reach of children. P103 Read label before use. P210 Keep away from heat/sparks/open flames/hot surfaces. - No smoking. P233 Keep container tightly closed"""
    sect14_sample = "TRANSPORT INFORMATION Regulation UN Number Proper Shipping Name DG Class Packing Group Label Additional Information ADG UN1987 ALCOHOLS, N.O.S. [Isopropyl Alcohol]"
    
    print("=== TESTING IMPROVEMENTS ===")
    
    # Test vendor extraction
    vendor = _extract_vendor_improved("", sect16_sample, "")
    print(f"Vendor: {vendor}")
    
    # Test signal word
    signal_word = _extract_signal_word(sect2_sample)
    print(f"Signal word: {signal_word}")
    
    # Test P-codes
    p_codes = _extract_precautionary_statements(sect2_sample)
    print(f"P-codes found: {len(p_codes)}")
    for p in p_codes[:3]:  # Show first 3
        print(f"  - {p}")
    
    # Test transport info
    is_dg, dg_class, pg, un, conf, subs = _dangerous_goods_tuple_improved(sect14_sample)
    print(f"Dangerous goods: {is_dg}")
    print(f"DG Class: {dg_class}")
    print(f"UN Number: {un}")
    
    # Test proper shipping name
    shipping_name = _extract_proper_shipping_name(sect14_sample)
    print(f"Proper shipping name: {shipping_name}")

if __name__ == "__main__":
    test_improvements()
