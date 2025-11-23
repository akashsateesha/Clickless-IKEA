import os
from datetime import datetime
from automation.ikea_cart import cart_manager
import logging

logger = logging.getLogger(__name__)

async def add_to_cart_with_state(product_url: str, product_name: str, product_price: str, cart_items: list) -> tuple:
    """Add a product to cart and update local state."""
    logger.info(f"Tool: Adding {product_url} to cart")
    result = await cart_manager.add_to_cart(product_url)
    
    if result['status'] == 'success':
        cart_items.append({
            'product_id': extract_product_id(product_url),
            'name': product_name,
            'url': product_url,
            'price': product_price,
            'added_at': datetime.now().isoformat()
        })
        
        video_file = result.get('video_path')
        if video_file:
            html = f"""<div class="success-message">
✅ {result.get('message', 'Successfully added product to cart')}
</div>
<div class="video-container">
    <video controls autoplay muted loop class="action-video">
        <source src="/videos/{video_file}" type="video/webm">
        Your browser does not support the video tag.
    </video>
</div>
<p><button onclick="navigator.clipboard.writeText('show me the cart'); document.querySelector('input[name=q]').value='show me the cart'; document.querySelector('form').submit();" style="padding: 10px 20px; background: #0058a3; color: white; border: none; border-radius: 8px; cursor: pointer; margin-top: 10px; font-weight: 600;">🛒 View Shopping Cart</button></p>"""
        else:
            html = f"""<div class="success-message">✅ {result.get('message')}</div>"""
        
        return html, cart_items
    else:
        return f"❌ Failed to add to cart: {result.get('message', 'Unknown error')}", cart_items

async def view_cart_with_state(cart_items: list) -> tuple:
    """View cart using local state and optionally get browser video."""
    logger.info("Tool: Viewing cart")
    
    html_parts = []
    if not cart_items:
        html_parts.append("<p>Your shopping cart is empty.</p>")
    else:
        html_parts.append(f"<p><strong>Your cart contains {len(cart_items)} item(s):</strong></p>")
        html_parts.append("<ul style='list-style: none; padding: 0;'>")
        for item in cart_items:
            html_parts.append(f"<li style='padding: 8px; margin: 4px 0; background: #f5f5f5; border-radius: 6px;'>• {item['name']} - {item['price']}</li>")
        html_parts.append("</ul>")
    
    try:
        result = await cart_manager.view_cart()
        if result['status'] == 'success':
            video_file = result.get('video_path')
            if video_file:
                html_parts.append(f"""
<div class="video-container">
    <video controls autoplay muted loop class="action-video">
        <source src="/videos/{video_file}" type="video/webm">
    </video>
</div>""")
    except Exception as e:
        logger.warning(f"Could not get cart video: {e}")
    
    return '\n'.join(html_parts), cart_items

async def remove_from_cart_with_state(item_index: int, cart_items: list) -> tuple:
    """Remove item from cart and update local state."""
    if item_index < 0 or item_index >= len(cart_items):
        return f"❌ Invalid item index: {item_index}", cart_items
    
    item = cart_items[item_index]
    logger.info(f"Tool: Removing {item['name']} from cart")
    
    removed_item = cart_items.pop(item_index)
    
    video_path = None
    try:
        result = await cart_manager.remove_from_cart(item['name'])
        if result['status'] == 'success':
            video_path = result.get('video_path')
    except Exception as e:
        logger.warning(f"Browser cart removal error: {e}")
    
    if video_path:
        html = f"""<div class="success-message">
✅ Removed '{removed_item['name']}' from cart
</div>
<div class="video-container">
    <video controls autoplay muted loop class="action-video">
        <source src="/videos/{video_path}" type="video/webm">
    </video>
</div>"""
    else:
        html = f"""<div class="success-message">✅ Removed '{removed_item['name']}' from cart</div>"""
    
    return html, cart_items

def extract_product_id(url: str) -> str:
    """Extract product ID from IKEA URL."""
    # URL format: https://.../ p/product-name-sku123/
    parts = url.rstrip('/').split('/')
    for part in reversed(parts):
        if part.startswith('s') and len(part) > 5:
            return part
    return ""
