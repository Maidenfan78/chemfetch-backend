#!/usr/bin/env python3
"""
Test script to debug SDS parsing issues
"""
import sys
import os
import subprocess

def test_parse_sds():
    """Test the parse_sds.py script with the failing URL"""
    test_url = "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF"
    test_product_id = 183
    
    print(f"Testing SDS parsing with URL: {test_url}")
    print(f"Product ID: {test_product_id}")
    
    try:
        # Run the parse_sds.py script with the same arguments
        result = subprocess.run([
            sys.executable, 
            "parse_sds.py",
            "--url", test_url,
            "--product-id", str(test_product_id)
        ], capture_output=True, text=True, timeout=120)
        
        print(f"Exit code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")
        
        if result.returncode == 0:
            print("✅ Success! Parsing completed.")
            # Try to parse the JSON output
            import json
            try:
                parsed = json.loads(result.stdout.strip())
                print("✅ JSON output is valid")
                print(f"Vendor: {parsed.get('vendor')}")
                print(f"Issue Date: {parsed.get('issue_date')}")
                print(f"Hazardous: {parsed.get('hazardous_substance')}")
                print(f"Dangerous Good: {parsed.get('dangerous_good')}")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON output: {e}")
        else:
            print(f"❌ Script failed with exit code {result.returncode}")
            
    except subprocess.TimeoutExpired:
        print("❌ Script timed out after 120 seconds")
    except Exception as e:
        print(f"❌ Error running script: {e}")

def check_dependencies():
    """Check if all required dependencies are available"""
    dependencies = [
        'pdfplumber',
        'requests', 
        'json',
        'argparse',
        'dataclasses',
        'datetime'
    ]
    
    print("Checking dependencies:")
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep} - MISSING")

if __name__ == "__main__":
    print("=== SDS Parsing Debug Script ===")
    check_dependencies()
    print("\n" + "="*40 + "\n")
    test_parse_sds()
