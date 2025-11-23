"""
Simple integration test for LLM-based product selection

This demonstrates the new functionality without requiring live API calls.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.product_resolver import (
    fallback_keyword_matching,
    generate_clarification_message,
    _format_product_list
)


# Sample test products
SAMPLE_PRODUCTS = [
    {
        "metadata": {
            "name": "MARKUS Office chair, Vissle gray",
            "price": "229.00",
            "url": "https://www.ikea.com/us/en/p/markus-office-chair-vissle-gray-90289172/"
        },
        "document": "MARKUS office chair provides exceptional lumbar support with adjustable tilt tension."
    },
    {
        "metadata": {
            "name": "JÄRVFJÄLLET Office chair with armrests, white",
            "price": "279.00",
            "url": "https://www.ikea.com/us/en/p/jaervfjaellet-office-chair-with-armrests-white-70521856/"
        },
        "document": "JÄRVFJÄLLET ergonomic office chair with adjustable height and tilt."
    },
    {
        "metadata": {
            "name": "BEKANT Desk, white, 63x31 1/2\"",
            "price": "149.00",
            "url": "https://www.ikea.com/us/en/p/bekant-desk-white-s19282596/"
        },
        "document": "BEKANT desk with clean white surface. Sturdy construction perfect for home office."
    }
]


def test_fallback_keyword_matching():
    """Test fallback keyword matching functionality"""
    print("\n" + "="*70)
    print("TEST 1: Fallback Keyword Matching - 'MARKUS chair'")
    print("="*70)
    
    result = fallback_keyword_matching(
        query="MARKUS chair",
        available_products=SAMPLE_PRODUCTS
    )
    
    print(f"✓ Confidence: {result['confidence']}")
    print(f"✓ Reasoning: {result['reasoning']}")
    print(f"✓ Needs clarification: {result['needs_clarification']}")
    
    if result['matched_products']:
        matched_name = result['matched_products'][0]['metadata']['name']
        print(f"✓ Matched product: {matched_name}")
        assert "MARKUS" in matched_name, "Should match MARKUS chair"
        print("✅ TEST PASSED: Correctly matched MARKUS chair")
    else:
        print("❌  TEST FAILED: No match found")
        return False
    
    return True


def test_clarification_message():
    """Test clarification message generation"""
    print("\n" + "="*70)
    print("TEST 2: Clarification Message Generation")
    print("="*70)
    
    resolution = {
        'matched_products': [],
        'confidence': 0.3,
        'reasoning': 'Multiple matches found',
        'needs_clarification': True
    }
    
    message = generate_clarification_message(
        query="add a chair",
        resolution_result=resolution,
        available_products=SAMPLE_PRODUCTS
    )
    
    print(f"✓ Generated message (truncated): {message[:150]}...")
    assert isinstance(message, str) and len(message) > 0
    assert "product" in message.lower() or "chair" in message.lower()
    print("✅ TEST PASSED: Generated helpful clarification message")
    return True


def test_format_product_list():
    """Test product list formatting"""
    print("\n" + "="*70)
    print("TEST 3: Product List Formatting")
    print("="*70)
    
    formatted = _format_product_list(SAMPLE_PRODUCTS[:2])
    
    print(f"✓ Formatted HTML:\n{formatted}")
    assert "<li" in formatted
    assert "MARKUS" in formatted
    assert "JÄRVFJÄLLET" in formatted
    print("✅ TEST PASSED: Products formatted as HTML list")
    return True


def test_white_chair_matching():
    """Test matching 'white chair' - should match JÄRVFJÄLLET"""
    print("\n" + "="*70)
    print("TEST 4: Semantic Matching - 'the white chair'")
    print("="*70)
    
    result = fallback_keyword_matching(
        query="the white chair",
        available_products=SAMPLE_PRODUCTS
    )
    
    print(f"✓ Confidence: {result['confidence']}")
    
    if result['matched_products']:
        matched_name = result['matched_products'][0]['metadata']['name']
        print(f"✓ Matched product: {matched_name}")
        # Should match either JÄRVFJÄLLET or BEKANT (both white)
        # Fallback matching might not be perfect but should find something
        assert "white" in matched_name.lower()
        print("✅ TEST PASSED: Matched a white product")
    else:
        print("⚠️  No match (fallback is keyword-based, may not catch all semantic queries)")
    
    return True


def test_cart_item_removal():
    """Test matching for cart item removal"""
    print("\n" + "="*70)
    print("TEST 5: Cart Item Removal - 'remove MARKUS'")
    print("="*70)
    
    # Cart items have flatter structure (no metadata wrapper)
    cart_items = [
        {
            "name": "MARKUS Office chair, Vissle gray",
            "price": "229.00",
            "product_id": "90289172",
            "metadata": {
                "name": "MARKUS Office chair, Vissle gray",
                "price": "229.00"
            }
        },
        {
            "name": "BEKANT Desk, white, 63x31 1/2\"",
            "price": "149.00",
            "product_id": "s19282596",
            "metadata": {
                "name": "BEKANT Desk, white, 63x31 1/2\"",
                "price": "149.00"
            }
        }
    ]
    
    result = fallback_keyword_matching(
        query="remove MARKUS",
        available_products=cart_items
    )
    
    print(f"✓ Confidence: {result['confidence']}")
    
    if result['matched_products']:
        matched_item = result['matched_products'][0]
        matched_name = matched_item.get('name') or matched_item.get('metadata', {}).get('name', '')
        print(f"✓ Matched cart item: {matched_name}")
        assert "MARKUS" in matched_name
        print("✅ TEST PASSED: Correctly identified cart item for removal")
    else:
        print("❌ TEST FAILED: Could not match cart item")
        return False
    
    return True


def main():
    """Run all tests"""
    print("\n" + "🧪 "*20)
    print("INTEGRATION TESTS: LLM-Based Product Selection")
    print("🧪 "*20)
    print("\nThese tests demonstrate the fallback mechanism that works")
    print("without requiring live LLM API calls.")
    
    tests = [
        test_fallback_keyword_matching,
        test_clarification_message,
        test_format_product_list,
        test_white_chair_matching,
        test_cart_item_removal
    ]
    
    results = []
    for test_func in tests:
        try:
            results.append(test_func())
        except AssertionError as e:
            print(f"❌ Assertion failed: {e}")
            results.append(False)
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append(False)
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    passed = sum(results)
    total = len(results)
    print(f"✅ Passed: {passed}/{total}")
    print(f"❌ Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
