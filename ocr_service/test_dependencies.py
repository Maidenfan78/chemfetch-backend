#!/usr/bin/env python3
"""
Test script to verify all dependencies are installed and working
"""

import json
import sys

def test_imports():
    """Test that all required imports work"""
    results = {}
    
    try:
        import requests
        results['requests'] = 'OK'
    except ImportError as e:
        results['requests'] = f'FAILED: {e}'
    
    try:
        import pdfplumber
        results['pdfplumber'] = 'OK'
    except ImportError as e:
        results['pdfplumber'] = f'FAILED: {e}'
    
    try:
        import pytesseract
        results['pytesseract'] = 'OK'
    except ImportError as e:
        results['pytesseract'] = f'FAILED: {e}'
    
    try:
        from PIL import Image
        results['PIL'] = 'OK'
    except ImportError as e:
        results['PIL'] = f'FAILED: {e}'
    
    try:
        import re
        results['re'] = 'OK'
    except ImportError as e:
        results['re'] = f'FAILED: {e}'
    
    try:
        from dataclasses import dataclass
        results['dataclasses'] = 'OK'
    except ImportError as e:
        results['dataclasses'] = f'FAILED: {e}'
    
    try:
        from datetime import datetime
        results['datetime'] = 'OK'
    except ImportError as e:
        results['datetime'] = f'FAILED: {e}'
    
    return results

if __name__ == '__main__':
    print("Testing Python dependencies...")
    results = test_imports()
    
    all_ok = all(status == 'OK' for status in results.values())
    
    print(json.dumps({
        'dependencies': results,
        'all_ok': all_ok,
        'python_version': sys.version
    }, indent=2))
    
    if not all_ok:
        sys.exit(1)
    else:
        print("All dependencies are available!")
