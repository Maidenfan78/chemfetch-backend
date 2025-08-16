#!/usr/bin/env python3
"""
Test the enhanced SDS parser improvements
"""

import json
import sys
import os

# Add the current directory to path so we can import parse_sds
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Test with the same URL as your original test
def test_improved_parser():
    """Test the parser improvements with the original URL"""
    
    # For now, let's run the existing parser and see what we get
    import subprocess
    
    # Run the original parser
    print("=== Testing original parser ===")
    result = subprocess.run([
        "python", "parse_sds.py", 
        "--url", "https://m.media-amazon.com/images/I/81heA4nSXUL.pdf",
        "--product-id", "174"
    ], capture_output=True, text=True, cwd=".")
    
    if result.returncode == 0:
        original_data = json.loads(result.stdout)
        print("Original parser extracted:")
        print(f"  - Product: {original_data.get('product_name')}")
        print(f"  - Vendor: {original_data.get('vendor')}")
        print(f"  - Hazard statements: {len(original_data.get('hazard_statements', []))}")
        print(f"  - Signal word: Not captured")
        print(f"  - P-codes: Not captured")
        print(f"  - Physical properties: Not captured")
        print(f"  - Dangerous goods class: {original_data.get('dangerous_goods_class')}")
        print(f"  - Proper shipping name: Not captured")
        
        # Analyze missing fields
        missing_fields = [k for k, v in original_data.items() if v is None]
        print(f"  - Missing fields: {missing_fields}")
    else:
        print(f"Error running original parser: {result.stderr}")

if __name__ == "__main__":
    test_improved_parser()
