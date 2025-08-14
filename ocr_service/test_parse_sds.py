#!/usr/bin/env python3
"""
SDS Parsing Test Script

This script allows you to test SDS parsing without command line arguments.
Simply modify the TEST_CASES below and run: python test_parse_sds.py
"""

from parse_sds import parse_sds_pdf
import json
import sys

# Test cases - modify these as needed
TEST_CASES = [
    {
        "product_id": 999,
        "pdf_url": "https://example.com/test-sds.pdf",
        "description": "Test SDS document"
    }
]

def test_parsing():
    """Test SDS parsing with predefined test cases"""
    print("🧪 SDS Parsing Test Script")
    print("=" * 50)
    
    if not TEST_CASES or not TEST_CASES[0]["pdf_url"] or "example.com" in TEST_CASES[0]["pdf_url"]:
        print("❌ No valid test cases configured!")
        print("\n📝 To use this script:")
        print("1. Edit the TEST_CASES list in this file")
        print("2. Add real SDS PDF URLs and product IDs")
        print("3. Run: python test_parse_sds.py")
        print("\n💡 Example test case:")
        print("""TEST_CASES = [
    {
        "product_id": 156,
        "pdf_url": "https://www.isocol.com.au/wp-content/uploads/2023/06/Isocol-Rubbing-Alcohol-SDS.pdf",
        "description": "Isocol Rubbing Alcohol"
    }
]""")
        return False
    
    success_count = 0
    total_count = len(TEST_CASES)
    
    for i, test_case in enumerate(TEST_CASES, 1):
        product_id = test_case["product_id"]
        pdf_url = test_case["pdf_url"]
        description = test_case.get("description", f"Test case {i}")
        
        print(f"\n🔍 Test {i}/{total_count}: {description}")
        print(f"📄 Product ID: {product_id}")
        print(f"🔗 PDF URL: {pdf_url}")
        print("-" * 30)
        
        try:
            result = parse_sds_pdf(pdf_url, product_id=product_id)
            print("✅ Parsing successful!")
            print("📊 Results:")
            
            # Pretty print the results
            result_dict = result.as_upsert_dict()
            for key, value in result_dict.items():
                if isinstance(value, list) and value:
                    print(f"  {key}: {', '.join(str(v) for v in value)}")
                elif value:
                    print(f"  {key}: {value}")
                else:
                    print(f"  {key}: [not found]")
            
            success_count += 1
            
        except Exception as e:
            print(f"❌ Parsing failed: {str(e)}")
            if "requests" in str(e).lower() or "connection" in str(e).lower():
                print("💡 Hint: Check your internet connection and PDF URL")
            elif "pdf" in str(e).lower():
                print("💡 Hint: The URL might not be a valid PDF")
    
    print("\n" + "=" * 50)
    print(f"📈 Results: {success_count}/{total_count} tests passed")
    
    if success_count == total_count:
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        return False

def interactive_test():
    """Interactive mode for testing single URLs"""
    print("\n🔧 Interactive SDS Parsing Test")
    print("Enter 'quit' to exit")
    
    while True:
        print("\n" + "-" * 30)
        try:
            pdf_url = input("📎 Enter PDF URL: ").strip()
            if pdf_url.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            
            if not pdf_url:
                continue
                
            if not pdf_url.startswith('http'):
                print("❌ Please enter a valid HTTP/HTTPS URL")
                continue
            
            product_id = input("🆔 Enter product ID (or press Enter for 999): ").strip()
            if not product_id:
                product_id = 999
            else:
                product_id = int(product_id)
            
            print(f"\n🔍 Testing: {pdf_url}")
            print("⏳ Parsing... (this may take up to 5 minutes)")
            
            result = parse_sds_pdf(pdf_url, product_id=product_id)
            print("\n✅ Parsing successful!")
            print("📊 Results:")
            
            result_dict = result.as_upsert_dict()
            for key, value in result_dict.items():
                if isinstance(value, list) and value:
                    print(f"  {key}: {', '.join(str(v) for v in value)}")
                elif value:
                    print(f"  {key}: {value}")
                else:
                    print(f"  {key}: [not found]")
                    
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except ValueError:
            print("❌ Please enter a valid product ID (number)")
        except Exception as e:
            print(f"❌ Parsing failed: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If arguments provided, use original behavior
        if len(sys.argv) != 3:
            print("Usage: python test_parse_sds.py")
            print("   OR: python test_parse_sds.py <PRODUCT_ID> <PDF_URL>")
            sys.exit(1)
        
        product_id = int(sys.argv[1])
        pdf_url = sys.argv[2]
        
        try:
            result = parse_sds_pdf(pdf_url, product_id=product_id)
            print(json.dumps(result.as_upsert_dict(), indent=2))
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Interactive/test mode
        print("🧪 SDS Parser Test Suite")
        print("Choose an option:")
        print("1. Run predefined test cases")
        print("2. Interactive testing mode")
        print("3. Exit")
        
        while True:
            try:
                choice = input("\nEnter choice (1-3): ").strip()
                if choice == "1":
                    test_parsing()
                    break
                elif choice == "2":
                    interactive_test()
                    break
                elif choice == "3":
                    print("👋 Goodbye!")
                    break
                else:
                    print("❌ Please enter 1, 2, or 3")
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
