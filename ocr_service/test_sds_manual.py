#!/usr/bin/env python3
"""
Manual SDS Testing Script
=========================

This script lets you easily test SDS parsing with various URLs or local files.
It extracts the key fields you need and displays them in a readable format.

Usage:
    python test_sds_manual.py
    
Then follow the prompts to enter URLs or file paths.
"""

import json
import os
import sys
from parse_sds import parse_sds_pdf, parse_sds_path, ParsedSds

def print_separator():
    print("=" * 80)

def print_results(result: ParsedSds):
    """Print the parsed results in a clean, readable format"""
    print_separator()
    print("📋 PARSED SDS RESULTS")
    print_separator()
    
    print(f"🆔 Product ID:           {result.product_id}")
    print(f"📦 Product Name:         {result.product_name or 'Not found'}")
    print(f"🏢 Vendor/Manufacturer:  {result.vendor or 'Not found'}")
    print(f"📅 Issue Date:           {result.issue_date or 'Not found'}")
    print(f"⚠️  Hazardous Substance:  {result.hazardous_substance} (confidence: {result.hazardous_confidence:.2f})")
    print(f"🚛 Dangerous Good:       {result.dangerous_good} (confidence: {result.dangerous_goods_confidence:.2f})")
    print(f"📊 DG Class:             {result.dangerous_goods_class or 'N/A'}")
    print(f"📦 Packing Group:        {result.packing_group or 'N/A'}")
    print(f"⚡ Subsidiary Risks:     {result.subsidiary_risks or 'N/A'}")
    print(f"🆔 UN Number:            {result.un_number or 'N/A'}")
    
    # Additional useful info
    if result.signal_word:
        print(f"⚠️  Signal Word:          {result.signal_word}")
    
    if result.hazard_statements:
        print(f"📝 Hazard Statements:    {len(result.hazard_statements)} found")
        for stmt in result.hazard_statements[:3]:  # Show first 3
            print(f"   • {stmt}")
        if len(result.hazard_statements) > 3:
            print(f"   ... and {len(result.hazard_statements) - 3} more")
    
    if result.cas_numbers:
        print(f"🧪 CAS Numbers:          {', '.join(result.cas_numbers)}")
    
    print_separator()

def test_url():
    """Test parsing from a URL"""
    print("\n🌐 Testing SDS parsing from URL")
    print("-" * 40)
    
    # Pre-defined test URLs
    test_urls = [
        "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF",
        "https://example.com/your-sds.pdf",  # Replace with your own
    ]
    
    print("Select a test URL or enter your own:")
    for i, url in enumerate(test_urls, 1):
        print(f"{i}. {url}")
    print("0. Enter custom URL")
    
    try:
        choice = input("\nChoice (0-{}): ".format(len(test_urls)))
        
        if choice == "0":
            url = input("Enter SDS URL: ").strip()
        else:
            url = test_urls[int(choice) - 1]
        
        if not url:
            print("❌ No URL provided")
            return
        
        print(f"\n🔄 Parsing SDS from: {url}")
        print("⏳ This may take 30-60 seconds...")
        
        result = parse_sds_pdf(url, product_id=999)
        print_results(result)
        
        # Save JSON output
        json_output = result.to_json()
        with open("last_test_result.json", "w") as f:
            f.write(json_output)
        print("💾 Full JSON saved to: last_test_result.json")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def test_file():
    """Test parsing from a local file"""
    print("\n📁 Testing SDS parsing from local file")
    print("-" * 40)
    
    file_path = input("Enter path to PDF file: ").strip()
    
    if not file_path:
        print("❌ No file path provided")
        return
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    try:
        print(f"\n🔄 Parsing SDS from: {file_path}")
        print("⏳ This may take 30-60 seconds...")
        
        result = parse_sds_path(file_path, product_id=999)
        print_results(result)
        
        # Save JSON output
        json_output = result.to_json()
        with open("last_test_result.json", "w") as f:
            f.write(json_output)
        print("💾 Full JSON saved to: last_test_result.json")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def quick_test():
    """Quick test with the known working URL"""
    print("\n⚡ Quick test with known SDS")
    print("-" * 40)
    
    url = "https://ehs.wuerth.com/ehs4customers/export/04131886.PDF"
    print(f"🔄 Testing with: {url}")
    print("⏳ This may take 30-60 seconds...")
    
    try:
        result = parse_sds_pdf(url, product_id=123)
        print_results(result)
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main interactive menu"""
    print("🧪 Manual SDS Parser Testing Tool")
    print("==================================")
    
    # Check if we're in the right directory
    if not os.path.exists("parse_sds.py"):
        print("❌ Error: parse_sds.py not found in current directory")
        print("💡 Please run this script from the ocr_service directory")
        return
    
    while True:
        print("\nWhat would you like to test?")
        print("1. 🌐 Parse SDS from URL")
        print("2. 📁 Parse SDS from local file")
        print("3. ⚡ Quick test (known working URL)")
        print("4. 🔧 Check dependencies")
        print("0. ❌ Exit")
        
        choice = input("\nChoice (0-4): ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        elif choice == "1":
            test_url()
        elif choice == "2":
            test_file()
        elif choice == "3":
            if quick_test():
                print("✅ Quick test completed successfully!")
            else:
                print("❌ Quick test failed")
        elif choice == "4":
            check_dependencies()
        else:
            print("❌ Invalid choice. Please try again.")

def check_dependencies():
    """Check if all required dependencies are available"""
    print("\n🔧 Checking Dependencies")
    print("-" * 40)
    
    required = ['pdfplumber', 'requests', 'dataclasses', 'datetime', 'json', 're']
    optional = ['fitz', 'pypdf', 'pdf2image', 'pytesseract']
    
    all_good = True
    
    print("Required dependencies:")
    for dep in required:
        try:
            __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep} - MISSING!")
            all_good = False
    
    print("\nOptional dependencies (for better performance):")
    for dep in optional:
        try:
            __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"⚠️  {dep} - missing (optional)")
    
    if all_good:
        print("\n✅ All required dependencies are available!")
    else:
        print("\n❌ Some required dependencies are missing.")
        print("💡 Run: pip install -r requirements.txt")

if __name__ == "__main__":
    main()
