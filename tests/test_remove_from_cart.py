import os
import sys
import asyncio
import pytest

# Ensure project root is in sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.ikea_cart import IKEACartManager
from automation.browser_manager import browser_manager

def test_remove_item_from_cart():
    """Test adding an item to the IKEA cart and then removing it, handling empty cart gracefully."""
    asyncio.run(_run_test())

async def _run_test():
    # Initialize browser (headless=False for visibility)
    await browser_manager.initialize(headless=False)
    manager = IKEACartManager()
    product_url = "https://www.ikea.com/us/en/p/markus-office-chair-vissle-dark-gray-90289172/"

    # Add to cart
    add_result = await manager.add_to_cart(product_url)
    assert add_result["status"] == "success"

    # View cart to get product name
    view_result = await manager.view_cart()
    assert view_result["status"] == "success"
    items = view_result.get("items", [])
    if items:
        product_name = items[0]["name"]
        # Remove the item
        remove_result = await manager.remove_from_cart(product_name)
        assert remove_result["status"] == "success"
        # Verify cart is empty
        view_after = await manager.view_cart()
        assert view_after["status"] == "success"
        if "items" in view_after:
            assert len(view_after["items"]) == 0
        else:
            assert "empty" in view_after.get("message", "").lower()
    else:
        # If cart is empty after add, ensure remove reports appropriate error
        remove_result = await manager.remove_from_cart("nonexistent")
        assert remove_result["status"] == "error"

    # Cleanup
    await browser_manager.close()
