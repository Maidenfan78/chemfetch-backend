#!/usr/bin/env python3
"""
Test the parsing functionality to verify it works
"""
import sys
import os
import subprocess
import json

def test_parsing():
    """Test the SDS parsing with the actual URL from the logs"""
    try:
        # Change to the correct directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        test_url = "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF"
        test_product_id = 183
        
        print(f"Testing with URL: {test_url}")
        print(f"Product ID: {test_product_id}")
        print(f"Working directory: {os.getcwd()}")
        
        # Test the exact command that the backend will run
        cmd = [
            sys.executable,
            "parse_sds.py", 
            "--product-id", str(test_product_id),
            "--url", test_url
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        print(f"Exit code: {result.returncode}")
        
        if result.stdout:
            print(f"STDOUT ({len(result.stdout)} chars):")
            print(result.stdout[:1000] + ("..." if len(result.stdout) > 1000 else ""))
            
        if result.stderr:
            print(f"STDERR:")
            print(result.stderr)
            
        if result.returncode == 0:
            try:
                # Try to parse the JSON output
                data = json.loads(result.stdout.strip())
                print("\n✅ SUCCESS! JSON parsed successfully")
                print(f"Vendor: {data.get('vendor', 'N/A')}")
                print(f"Product ID: {data.get('product_id', 'N/A')}")
                print(f"Issue Date: {data.get('issue_date', 'N/A')}")
                print(f"Hazardous Substance: {data.get('hazardous_substance', 'N/A')}")
                print(f"Dangerous Good: {data.get('dangerous_good', 'N/A')}")
                print(f"Dangerous Goods Class: {data.get('dangerous_goods_class', 'N/A')}")
                return True
            except json.JSONDecodeError as e:
                print(f"\n❌ JSON parsing failed: {e}")
                return False
        else:
            print(f"\n❌ Script failed with exit code {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print("\n❌ Script timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_dependencies():
    """Check if required dependencies are available"""
    required_deps = ['pdfplumber', 'requests']
    optional_deps = ['fitz', 'pypdf']
    
    print("Checking dependencies:")
    
    for dep in required_deps:
        try:
            __import__(dep)
            print(f"✅ {dep} (required)")
        except ImportError:
            print(f"❌ {dep} (required) - MISSING!")
            
    for dep in optional_deps:
        try:
            __import__(dep)
            print(f"✅ {dep} (optional)")
        except ImportError:
            print(f"⚠️  {dep} (optional) - missing")

if __name__ == "__main__":
    print("=== SDS Parsing Test ===")
    print()
    
    # Check dependencies first
    check_dependencies()
    print()
    
    # Test the parsing
    success = test_parsing()
    
    print()
    if success:
        print("🎉 Test completed successfully! The auto-parsing should now work.")
    else:
        print("💥 Test failed. Check the error messages above.")
