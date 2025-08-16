#!/usr/bin/env python3
"""
Simple test to validate parse_sds.py works correctly
"""
import json
import subprocess
import sys
import os

def test_basic_import():
    """Test if we can import the parse_sds module"""
    try:
        # Change to the ocr_service directory
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        # Try importing the parse_sds functions
        from parse_sds import parse_sds_pdf, ParsedSds
        print("✅ Successfully imported parse_sds functions")
        return True
    except Exception as e:
        print(f"❌ Failed to import parse_sds: {e}")
        return False

def test_direct_call():
    """Test calling parse_sds_pdf directly"""
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        from parse_sds import parse_sds_pdf
        
        test_url = "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF"
        print(f"Testing direct function call with URL: {test_url}")
        
        result = parse_sds_pdf(test_url, product_id=183)
        print("✅ Direct function call succeeded")
        print(f"Vendor: {result.vendor}")
        print(f"Hazardous: {result.hazardous_substance}")
        print(f"Dangerous Good: {result.dangerous_good}")
        
        return True
    except Exception as e:
        print(f"❌ Direct function call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cli_call():
    """Test calling the script via command line"""
    try:
        test_url = "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF"
        
        result = subprocess.run([
            sys.executable, 
            "parse_sds.py",
            "--url", test_url,
            "--product-id", "183"
        ], capture_output=True, text=True, timeout=60, cwd=os.path.dirname(os.path.abspath(__file__)))
        
        print(f"CLI Exit code: {result.returncode}")
        if result.stdout:
            print(f"CLI Stdout: {result.stdout[:500]}...")
        if result.stderr:
            print(f"CLI Stderr: {result.stderr}")
            
        if result.returncode == 0:
            print("✅ CLI call succeeded")
            # Try parsing the JSON
            try:
                parsed = json.loads(result.stdout.strip())
                print("✅ JSON output is valid")
                return True
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON: {e}")
                return False
        else:
            print("❌ CLI call failed")
            return False
            
    except Exception as e:
        print(f"❌ CLI test error: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing parse_sds.py ===")
    
    print("\n1. Testing basic imports...")
    import_ok = test_basic_import()
    
    if import_ok:
        print("\n2. Testing direct function call...")
        direct_ok = test_direct_call()
        
        print("\n3. Testing CLI call...")
        cli_ok = test_cli_call()
        
        if direct_ok and cli_ok:
            print("\n✅ All tests passed! The script should work.")
        else:
            print("\n❌ Some tests failed. Check errors above.")
    else:
        print("\n❌ Cannot proceed with testing due to import errors.")
