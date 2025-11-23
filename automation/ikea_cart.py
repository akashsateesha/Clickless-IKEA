import asyncio
import logging
import os
from datetime import datetime
from automation.browser_manager import browser_manager

logger = logging.getLogger(__name__)

class IKEACartManager:
    """
    Handles IKEA-specific cart interactions with video recording.
    """
    
    def __init__(self):
        # Create screenshots/videos directory if it doesn't exist
        self.screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screenshots')
        self.videos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.videos_dir, exist_ok=True)
    
    async def _save_state(self, page):
        """Save browser state (cookies, local storage) to file."""
        try:
            state_path = os.path.join(os.path.dirname(self.screenshots_dir), 'browser_state.json')
            await page.context.storage_state(path=state_path)
            logger.info(f"Browser state saved to {state_path}")
        except Exception as e:
            logger.warning(f"Failed to save browser state: {e}")

    async def _load_state(self, page, target_url=None):
        """Load browser state (cookies and localStorage) from file."""
        try:
            state_path = os.path.join(os.path.dirname(self.screenshots_dir), 'browser_state.json')
            if not os.path.exists(state_path):
                return False
                
            import json
            with open(state_path, 'r') as f:
                state = json.load(f)
                
            # Restore cookies first
            if 'cookies' in state:
                await page.context.add_cookies(state['cookies'])
                logger.info("Restored cookies from saved state")
            
            # If target_url is provided, navigate to it first
            if target_url:
                await page.goto(target_url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_load_state("domcontentloaded")
            
            # Restore localStorage for www.ikea.com origin
            if 'origins' in state:
                for origin_data in state['origins']:
                    origin = origin_data.get('origin')
                    if origin and origin.startswith('https://www.ikea.com'):
                        local_storage = origin_data.get('localStorage', [])
                        if local_storage:
                            try:
                                for item in local_storage:
                                    await page.evaluate(
                                        f"""localStorage.setItem({json.dumps(item['name'])}, {json.dumps(item['value'])})"""
                                    )
                                logger.info(f"Restored {len(local_storage)} localStorage items")
                            except Exception as e:
                                logger.debug(f"Could not restore localStorage: {e}")
                        break
            return True
        except Exception as e:
            logger.warning(f"Failed to load browser state: {e}")
            return False

    async def add_to_cart(self, product_url: str) -> dict:
        """
        Navigates to a product page and adds it to the cart (Recorded).
        """
        page = None
        context = None
        try:
            # Create VIDEO page
            page, context = await browser_manager.create_video_page()
            
            # Restore browser state
            await self._load_state(page)

            logger.info(f"Navigating to {product_url}...")
            await page.goto(product_url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            
            # Try to find the button
            add_btn_selectors = [
                "button[aria-label='Add to bag']",
                ".pip-btn--emphasised",
                "//span[contains(text(), 'Add to bag')]/ancestor::button",
                "button:has-text('Add to bag')"
            ]
            
            clicked = False
            for selector in add_btn_selectors:
                try:
                    await page.wait_for_selector(selector, state="visible", timeout=2000)
                    await page.click(selector)
                    logger.info(f"Clicked 'Add to bag' using: {selector}")
                    clicked = True
                    break
                except:
                    continue
            
            if not clicked:
                await context.close()
                return {"status": "error", "message": "Could not find 'Add to bag' button"}
            
            # Wait for confirmation
            try:
                await page.wait_for_selector("text=Added to bag", timeout=5000)
            except:
                # Fallback wait if modal doesn't appear
                await asyncio.sleep(3)
                
            # SAVE STATE
            await self._save_state(page)
            
            # Close context to save video
            await context.close()
            
            # Rename video
            video_path = await page.video.path()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_video_name = f"add_cart_{timestamp}.webm"
            new_video_path = os.path.join(self.videos_dir, new_video_name)
            os.rename(video_path, new_video_path)
            
            return {
                "status": "success", 
                "message": "Item added to cart",
                "video_path": new_video_name
            }
                
        except Exception as e:
            logger.error(f"Error adding to cart: {e}")
            if context: await context.close()
            return {"status": "error", "message": str(e)}

    async def view_cart(self) -> dict:
        """
        Navigates to the cart page and returns contents (Recorded).
        """
        page = None
        context = None
        try:
            # Create VIDEO page
            page, context = await browser_manager.create_video_page()
            
            # Restore browser state and navigate
            await self._load_state(page, target_url="https://www.ikea.com/us/en/shoppingcart/")
            await asyncio.sleep(3) # Wait for render
            
            # Scrape items
            items = []
            try:
                remove_buttons = await page.query_selector_all("button[aria-label*='Remove']")
                for button in remove_buttons:
                    aria_label = await button.get_attribute('aria-label')
                    if aria_label and aria_label.startswith('Remove '):
                        product_info = aria_label.replace('Remove ', '')
                        name = product_info.split(',')[0].strip()
                        items.append({"name": name, "price": "N/A"})
            except:
                pass
            
            # SAVE STATE
            await self._save_state(page)
            
            # Close context to save video
            await context.close()
            
            # Rename video
            video_path = await page.video.path()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_video_name = f"view_cart_{timestamp}.webm"
            new_video_path = os.path.join(self.videos_dir, new_video_name)
            os.rename(video_path, new_video_path)
            
            return {
                "status": "success",
                "items": items,
                "message": f"Found {len(items)} item(s) in cart",
                "video_path": new_video_name
            }
            
        except Exception as e:
            logger.error(f"Error viewing cart: {e}")
            if context: await context.close()
            return {"status": "error", "message": str(e)}
    
    async def remove_from_cart(self, product_name: str) -> dict:
        """
        Removes an item from the cart (Recorded).
        """
        page = None
        context = None
        try:
            # Create VIDEO page
            page, context = await browser_manager.create_video_page()

            await self._load_state(page, target_url='https://www.ikea.com/us/en/shoppingcart/')
            await asyncio.sleep(3)

            # Find remove button
            remove_buttons = await page.query_selector_all("button[aria-label*='Remove' ]")
            core_name = product_name.split(',')[0].strip().split()[0]
            
            remove_clicked = False
            for button in remove_buttons:
                aria_label = await button.get_attribute('aria-label')
                if aria_label and core_name.upper() in aria_label.upper():
                    await button.click()
                    remove_clicked = True
                    break

            if not remove_clicked:
                await context.close()
                return {'status': 'error', 'message': f'Could not find remove button for "{product_name}"'}

            await asyncio.sleep(2) # Wait for removal animation

            # SAVE STATE
            await self._save_state(page)
            
            # Close context to save video
            await context.close()
            
            # Rename video
            video_path = await page.video.path()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_video_name = f"remove_cart_{timestamp}.webm"
            new_video_path = os.path.join(self.videos_dir, new_video_name)
            os.rename(video_path, new_video_path)
            
            return {
                'status': 'success',
                'message': f"Removed {product_name} from cart",
                'video_path': new_video_name
            }
        except Exception as e:
            logger.error(f"Error removing from cart: {e}")
            if context: await context.close()
            return {'status': 'error', 'message': str(e)}

# Create singleton instance
cart_manager = IKEACartManager()
