"""
IKEA Chair Scraper
Scrapes chair product data from IKEA website using Playwright
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup
import aiohttp


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IKEAChairScraper:
    """
    Scrapes IKEA chair products with detailed information.
    
    Features:
    - Async scraping for performance
    - Rate limiting to avoid blocking
    - Retry logic for failed requests
    - Comprehensive data extraction
    """
    
    def __init__(
        self,
        base_url: str = "https://www.ikea.com/us/en",
        headless: bool = True,
        rate_limit: float = 2.0,  # seconds between requests
        max_retries: int = 3
    ):
        self.base_url = base_url
        self.headless = headless
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        
        # Data storage
        self.products: List[Dict] = []
        
        # Statistics
        self.stats = {
            "total_products": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "start_time": None,
            "end_time": None
        }
    
    async def init_browser(self):
        """Initialize Playwright browser"""
        logger.info("Initializing browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        self.page = await self.context.new_page()
        logger.info("Browser initialized successfully")
    
    async def close_browser(self):
        """Close browser and cleanup"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")
    
    async def navigate_with_retry(self, url: str, retries: int = 3) -> bool:
        """Navigate to URL with retry logic"""
        for attempt in range(retries):
            try:
                logger.info(f"Navigating to {url} (attempt {attempt + 1}/{retries})")
                await self.page.goto(url, wait_until='networkidle', timeout=30000)
                await asyncio.sleep(self.rate_limit)  # Rate limiting
                return True
            except Exception as e:
                logger.warning(f"Navigation failed (attempt {attempt + 1}): {str(e)}")
                if attempt == retries - 1:
                    logger.error(f"Failed to navigate to {url} after {retries} attempts")
                    return False
                await asyncio.sleep(2 * (attempt + 1))  # Exponential backoff
        return False
    
    async def get_chair_category_urls(self) -> List[str]:
        """
        Get all chair category URLs from IKEA
        Returns list of category page URLs
        """
        # IKEA chair categories
        chair_categories = [
            "/cat/chairs-fu003/",  # All chairs
            "/cat/office-chairs-20652/",  # Office chairs
            "/cat/dining-chairs-25219/",  # Dining chairs
            "/cat/armchairs-chaise-longues-fu039/",  # Armchairs
        ]
        
        urls = [urljoin(self.base_url, cat) for cat in chair_categories]
        logger.info(f"Found {len(urls)} chair categories")
        return urls
    
    async def get_product_urls_from_category(self, category_url: str) -> List[str]:
        """
        Extract all product URLs from a category page
        """
        product_urls = []
        
        if not await self.navigate_with_retry(category_url):
            return product_urls
        
        try:
            # Wait for products to load
            await self.page.wait_for_selector('.plp-product-list', timeout=10000)
            
            # Scroll to load all products (lazy loading)
            await self.scroll_to_bottom()
            
            # Extract product links
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Find all product cards
            product_cards = soup.select('div[class*="plp-fragment-wrapper"] a[href*="/p/"]')
            
            for card in product_cards:
                href = card.get('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    if full_url not in product_urls:
                        product_urls.append(full_url)
            
            logger.info(f"Found {len(product_urls)} products in category {category_url}")
            
        except Exception as e:
            logger.error(f"Error extracting products from {category_url}: {str(e)}")
        
        return product_urls
    
    async def scroll_to_bottom(self, max_scrolls: int = 10):
        """Scroll to bottom of page to trigger lazy loading"""
        for i in range(max_scrolls):
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)
            
            # Check if we've reached the bottom
            is_at_bottom = await self.page.evaluate(
                '(window.innerHeight + window.scrollY) >= document.body.scrollHeight'
            )
            if is_at_bottom:
                break
    
    async def scrape_product_details(self, product_url: str) -> Optional[Dict]:
        """
        Scrape detailed information from a product page
        """
        if not await self.navigate_with_retry(product_url):
            self.stats["failed_scrapes"] += 1
            return None
        
        try:
            # Wait for key elements
            await self.page.wait_for_selector('.pip-header-section', timeout=10000)
            
            content = await self.page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            # Extract product ID from URL
            product_id = self.extract_product_id(product_url)
            
            # Extract product name
            name = self.extract_name(soup)
            
            # Extract price
            price_data = self.extract_price(soup)
            
            # Extract description
            description = self.extract_description(soup)
            
            # Extract specifications
            specifications = self.extract_specifications(soup)
            
            # Extract features
            features = self.extract_features(soup)
            
            # Extract images
            images = await self.extract_images()
            
            # Extract reviews/ratings
            rating_data = self.extract_ratings(soup)
            
            # Extract availability
            availability = self.extract_availability(soup)
            
            # Extract materials and care instructions
            materials = self.extract_materials(soup)
            
            # Build product data
            product_data = {
                "product_id": product_id,
                "name": name,
                "price": price_data.get("price"),
                "currency": price_data.get("currency", "USD"),
                "description": description,
                "specifications": specifications,
                "features": features,
                "images": images,
                "availability": availability.get("available", False),
                "stock_status": availability.get("status", "unknown"),
                "rating": rating_data.get("rating"),
                "review_count": rating_data.get("count", 0),
                "materials": materials,
                "product_url": product_url,
                "category": "chairs",
                "subcategory": self.determine_subcategory(name, description),
                "scraped_at": datetime.now().isoformat(),
                "metadata": {
                    "full_text": self.create_full_text(name, description, features, specifications)
                }
            }
            
            logger.info(f"Successfully scraped: {name} (${price_data.get('price', 'N/A')})")
            self.stats["successful_scrapes"] += 1
            
            return product_data
            
        except Exception as e:
            logger.error(f"Error scraping product {product_url}: {str(e)}")
            self.stats["failed_scrapes"] += 1
            return None
    
    def extract_product_id(self, url: str) -> str:
        """Extract product ID from URL"""
        # URL format: .../product-name/S12345678
        parts = url.rstrip('/').split('/')
        for part in reversed(parts):
            if part.startswith('S') or part.startswith('s'):
                return part
        return url.split('/')[-1]
    
    def extract_name(self, soup: BeautifulSoup) -> str:
        """Extract product name"""
        name_elem = soup.select_one('.pip-header-section h1, .pip-product-summary__name')
        return name_elem.get_text(strip=True) if name_elem else "Unknown Product"
    
    def extract_price(self, soup: BeautifulSoup) -> Dict:
        """Extract price information"""
        price_elem = soup.select_one('.pip-temp-price__integer, .pip-price__integer')
        
        if price_elem:
            price_text = price_elem.get_text(strip=True).replace('$', '').replace(',', '')
            try:
                price = float(price_text)
            except ValueError:
                price = None
        else:
            price = None
        
        return {
            "price": price,
            "currency": "USD"
        }
    
    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract product description"""
        desc_elem = soup.select_one('.pip-product-summary__description, .pip-header-section__description')
        return desc_elem.get_text(strip=True) if desc_elem else ""
    
    def extract_specifications(self, soup: BeautifulSoup) -> Dict:
        """Extract product specifications (dimensions, weight, etc.)"""
        specs = {}
        
        # Find specifications table/list
        spec_section = soup.select('.pip-product-dimensions__measurement-wrapper, .pip-measurements__measurement')
        
        for spec in spec_section:
            label_elem = spec.select_one('.pip-measurements__measurement-name')
            value_elem = spec.select_one('.pip-measurements__measurement-value')
            
            if label_elem and value_elem:
                label = label_elem.get_text(strip=True).lower()
                value = value_elem.get_text(strip=True)
                specs[label] = value
        
        return specs
    
    def extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract product features"""
        features = []
        
        # Find features list
        feature_section = soup.select('.pip-product-details__container li, .pip-key-features li')
        
        for feature in feature_section:
            text = feature.get_text(strip=True)
            if text and len(text) > 3:
                features.append(text)
        
        return features[:10]  # Limit to top 10 features
    
    async def extract_images(self) -> List[str]:
        """Extract product images"""
        images = []
        
        try:
            # Find all image elements
            image_elements = await self.page.query_selector_all('.pip-media-grid__thumbnail img, .pip-aspect-ratio-image img')
            
            for img in image_elements[:5]:  # Limit to 5 images
                src = await img.get_attribute('src')
                if src and 'http' in src:
                    images.append(src)
        
        except Exception as e:
            logger.warning(f"Error extracting images: {str(e)}")
        
        return images
    
    def extract_ratings(self, soup: BeautifulSoup) -> Dict:
        """Extract rating and review count"""
        rating_elem = soup.select_one('.pip-header-section__rating-wrapper [class*="rating"]')
        
        rating = None
        count = 0
        
        if rating_elem:
            # Extract rating value (varies by IKEA region)
            rating_text = rating_elem.get('aria-label', '')
            try:
                # Parse "4.5 out of 5 stars"
                if 'out of' in rating_text:
                    rating = float(rating_text.split()[0])
            except (ValueError, IndexError):
                pass
        
        # Extract review count
        count_elem = soup.select_one('.pip-header-section__rating-count')
        if count_elem:
            count_text = count_elem.get_text(strip=True)
            try:
                count = int(''.join(filter(str.isdigit, count_text)))
            except ValueError:
                pass
        
        return {
            "rating": rating,
            "count": count
        }
    
    def extract_availability(self, soup: BeautifulSoup) -> Dict:
        """Extract availability information"""
        avail_elem = soup.select_one('.pip-product-availability, .pip-stockcheck')
        
        if avail_elem:
            text = avail_elem.get_text(strip=True).lower()
            available = 'in stock' in text or 'available' in text
            status = text if len(text) < 100 else "Check store"
        else:
            available = True  # Assume available if not specified
            status = "Available online"
        
        return {
            "available": available,
            "status": status
        }
    
    def extract_materials(self, soup: BeautifulSoup) -> List[str]:
        """Extract material information"""
        materials = []
        
        # Find materials section
        material_section = soup.select('.pip-product-details__container')
        
        for section in material_section:
            text = section.get_text()
            if 'material' in text.lower():
                # Extract material names
                material_items = section.select('li, p')
                for item in material_items:
                    mat_text = item.get_text(strip=True)
                    if mat_text and len(mat_text) < 100:
                        materials.append(mat_text)
        
        return materials[:5]  # Limit to 5 materials
    
    def determine_subcategory(self, name: str, description: str) -> str:
        """Determine chair subcategory based on name/description"""
        text = (name + " " + description).lower()
        
        if any(word in text for word in ['office', 'desk', 'task', 'swivel']):
            return 'office'
        elif any(word in text for word in ['dining', 'kitchen']):
            return 'dining'
        elif any(word in text for word in ['arm', 'lounge', 'recliner']):
            return 'armchair'
        elif any(word in text for word in ['outdoor', 'garden', 'patio']):
            return 'outdoor'
        elif any(word in text for word in ['bar', 'stool', 'counter']):
            return 'bar_stool'
        else:
            return 'general'
    
    def create_full_text(self, name: str, description: str, features: List[str], specs: Dict) -> str:
        """Create full text for embedding generation"""
        parts = [
            f"Name: {name}",
            f"Description: {description}",
            f"Features: {', '.join(features)}",
            f"Specifications: {', '.join([f'{k}: {v}' for k, v in specs.items()])}"
        ]
        return " | ".join(parts)
    
    async def scrape_all_chairs(self, max_products: Optional[int] = None) -> List[Dict]:
        """
        Main scraping method - scrapes all chair products
        
        Args:
            max_products: Maximum number of products to scrape (None = all)
        
        Returns:
            List of product dictionaries
        """
        self.stats["start_time"] = datetime.now()
        
        try:
            await self.init_browser()
            
            # Get all category URLs
            category_urls = await self.get_chair_category_urls()
            
            # Collect all product URLs
            all_product_urls = []
            for category_url in category_urls:
                product_urls = await self.get_product_urls_from_category(category_url)
                all_product_urls.extend(product_urls)
            
            # Remove duplicates
            all_product_urls = list(set(all_product_urls))
            
            # Limit if specified
            if max_products:
                all_product_urls = all_product_urls[:max_products]
            
            self.stats["total_products"] = len(all_product_urls)
            logger.info(f"Found {len(all_product_urls)} unique products to scrape")
            
            # Scrape each product
            for i, product_url in enumerate(all_product_urls, 1):
                logger.info(f"Scraping product {i}/{len(all_product_urls)}")
                
                product_data = await self.scrape_product_details(product_url)
                
                if product_data:
                    self.products.append(product_data)
                
                # Progress update every 10 products
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(all_product_urls)} products scraped")
            
            self.stats["end_time"] = datetime.now()
            self.print_stats()
            
            return self.products
            
        except Exception as e:
            logger.error(f"Error in scrape_all_chairs: {str(e)}")
            raise
        
        finally:
            await self.close_browser()
    
    def save_to_json(self, filepath: str = None):
        """Save scraped data to JSON file"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/raw/ikea_chairs_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "products": self.products,
                "stats": self.stats,
                "scraped_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved to {filepath}")
        return filepath
    
    def print_stats(self):
        """Print scraping statistics"""
        duration = (self.stats["end_time"] - self.stats["start_time"]).total_seconds()
        
        logger.info("=" * 50)
        logger.info("SCRAPING STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Total products found: {self.stats['total_products']}")
        logger.info(f"Successfully scraped: {self.stats['successful_scrapes']}")
        logger.info(f"Failed scrapes: {self.stats['failed_scrapes']}")
        logger.info(f"Success rate: {self.stats['successful_scrapes'] / max(self.stats['total_products'], 1) * 100:.1f}%")
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Average time per product: {duration / max(self.stats['successful_scrapes'], 1):.1f} seconds")
        logger.info("=" * 50)


# Example usage
async def main():
    """Example usage of the scraper"""
    scraper = IKEAChairScraper(
        headless=True,  # Set to False to see browser
        rate_limit=2.0   # 2 seconds between requests
    )
    
    # Scrape first 20 products for testing
    products = await scraper.scrape_all_chairs(max_products=20)
    
    # Save to JSON
    filepath = scraper.save_to_json()
    
    print(f"\nScraped {len(products)} products")
    print(f"Data saved to: {filepath}")


if __name__ == "__main__":
    asyncio.run(main())
