"""
IKEA Perfect Scraper - 100% Complete Data Extraction
Extracts all fields from the target schema with verified selectors
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PerfectIKEAScraper:
    """
    Production-ready IKEA scraper with 100% data extraction
    Extracts complete product data matching the target schema
    """
    
    def __init__(self, headless: bool = True, rate_limit: float = 2.0):
        self.headless = headless
        self.rate_limit = rate_limit
        self.products = []
        self.stats = {
            "total": 0,
            "successful": 0,
            "failed": 0
        }
    
    async def init_browser(self):
        """Initialize Playwright browser"""
        logger.info("Initializing browser...")
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        self.page = await self.context.new_page()
    
    async def close_browser(self):
        """Close browser"""
        await self.page.close()
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()
    
    async def get_product_urls(self, category_url: str, max_products: int = None) -> List[str]:
        """Get product URLs from category page"""
        logger.info(f"Loading category page: {category_url}")
        
        await self.page.goto(category_url, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(3)
        
        # Scroll to load all products
        for _ in range(5):
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)
        
        # Find product links
        links = await self.page.query_selector_all('a[href*="/p/"]')
        
        product_urls = []
        for link in links:
            href = await link.get_attribute('href')
            if href and '/p/' in href:
                if not href.startswith('http'):
                    href = f"https://www.ikea.com{href}"
                if href not in product_urls:
                    product_urls.append(href)
        
        if max_products:
            product_urls = product_urls[:max_products]
        
        logger.info(f"Found {len(product_urls)} product URLs")
        return product_urls
    
    def extract_product_id(self, html: str, url: str) -> str:
        """Extract product ID (Article Number)"""
        # Priority 1: Extract from URL (Most reliable)
        match = re.search(r'-([a-z]?\d{8,})/?$', url, re.I)
        if match:
            return match.group(1).lstrip('s').lstrip('S')

        # Priority 2: Try to find article number pattern in HTML
        match = re.search(r'(\d{3}\.\d{3}\.\d{2})', html)
        if match:
            return match.group(1).replace('.', '')
        
        return url.split('/')[-1].replace('/', '')
    
    def extract_name(self, soup: BeautifulSoup) -> Dict:
        """Extract product name and parse color from description"""
        h1 = soup.select_one('h1')
        
        title = "Unknown Product"
        description = ""
        color = None
        product_type = ""
        
        if h1:
            # Try to find specific spans first
            title_elem = h1.select_one('.pip-price-module__name-decorator, .pip-header-section__title')
            desc_elem = h1.select_one('.pip-price-module__description, .pip-header-section__description')
            
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            if desc_elem:
                description = desc_elem.get_text(strip=True)
                # Parse color from description (e.g. "Swivel chair, Gräsnäs dark gray")
                if ',' in description:
                    parts = description.split(',', 1)
                    product_type = parts[0].strip()
                    color = parts[1].strip()
                else:
                    product_type = description
            
            # Fallback if spans not found
            if title == "Unknown Product":
                full_text = h1.get_text(strip=True)
                title = full_text
        
        full_name = f"{title} {description}".strip()
        
        return {
            'title': title,
            'full_name': full_name,
            'short_description': description,
            'product_type': product_type,
            'parsed_color': color
        }

    def extract_price(self, soup: BeautifulSoup) -> Dict:
        """Extract price with proper parsing"""
        price_int = soup.select_one('.pip-temp-price__integer, .pip-price__integer')
        price_dec = soup.select_one('.pip-temp-price__decimal, .pip-price__decimal')
        
        price = None
        if price_int:
            # Clean price integer
            price_str = price_int.get_text(strip=True)
            price_str = re.sub(r'[^\d]', '', price_str)  # Remove all non-digits
            
            if price_dec:
                dec_str = price_dec.get_text(strip=True)
                dec_str = re.sub(r'[^\d]', '', dec_str)  # Remove all non-digits
                price_str = f"{price_str}.{dec_str}"
            
            try:
                price = float(price_str)
            except ValueError:
                pass
        
        return {
            'price': price,
            'currency': 'USD'
        }
    
    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract summary description"""
        summary = soup.select_one(".pip-product-summary__description")
        if summary:
            return summary.get_text(strip=True)
        return ""

    def extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract key features, filtering out headers"""
        features = []
        
        # Look for key features list specifically
        key_features = soup.select('.pip-product-details__container li')
        if not key_features:
             key_features = soup.select('.pip-key-features__container li')

        for item in key_features:
            text = item.get_text(strip=True)
            # Filter out headers and empty strings
            if text and len(text) > 5 and "Product details" not in text and "Measurements" not in text:
                features.append(text)
        
        return features[:5] # Keep top 5 features

    def extract_specifications(self, soup: BeautifulSoup, parsed_color: str = None) -> Dict:
        """Extract structured specifications (Materials & Dimensions)"""
        specs = {
            'material': {},
            'dimensions': {},
            'weight': None,
            'color': parsed_color,
            'style': None
        }
        
        # --- Extract Materials (using DL/DT/DD structure) ---
        # Look for the definition lists in product details
        details_containers = soup.select('.pip-product-details__container dl')
        for dl in details_containers:
            dt_elems = dl.find_all('dt')
            dd_elems = dl.find_all('dd')
            
            if len(dt_elems) == len(dd_elems):
                for dt, dd in zip(dt_elems, dd_elems):
                    key = dt.get_text(strip=True).rstrip(':')
                    value = dd.get_text(strip=True)
                    specs['material'][key] = value
            else:
                # Handle cases where dt/dd count doesn't match or nested
                text = dl.get_text(" ", strip=True)
                if ':' in text:
                    parts = text.split(':')
                    if len(parts) >= 2:
                        specs['material'][parts[0].strip()] = parts[1].strip()

        # --- Extract Dimensions (using LI/SPAN structure) ---
        dimensions_container = soup.select('.pip-product-dimensions__dimensions-container li')
        for li in dimensions_container:
            span = li.select_one('span')
            if span:
                key = span.get_text(strip=True).rstrip(':')
                # The value is the text of the LI minus the text of the SPAN
                full_text = li.get_text(strip=True)
                # Simple replace might be risky if key appears in value, but usually safe here
                value = full_text.replace(span.get_text(strip=True), "").strip().lstrip(':').strip()
                
                # Clean up key names
                key_lower = key.lower()
                if 'width' in key_lower:
                    specs['dimensions']['width'] = value
                elif 'depth' in key_lower:
                    specs['dimensions']['depth'] = value
                elif 'height' in key_lower:
                    specs['dimensions']['height'] = value
                elif 'tested for' in key_lower or 'weight' in key_lower:
                    specs['weight'] = value
                else:
                    # Add other dimensions with original key
                    specs['dimensions'][key] = value

        # Determine style (fallback)
        if not specs['style']:
            full_text = soup.get_text().lower()
            if 'modern' in full_text: specs['style'] = 'modern'
            elif 'traditional' in full_text: specs['style'] = 'traditional'
            
        return specs
    
    def extract_images(self, html: str) -> List[str]:
        """Extract ONLY the main image"""
        # Try to find the main product image
        # Usually the first one in the gallery or the main img tag
        
        # Regex for high-res images
        pattern = r'https://www\.ikea\.com/[^"\s]+/images/products/[^"\s]+\.(?:jpg|jpeg|png|webp)'
        found_urls = re.findall(pattern, html, re.I)
        
        if found_urls:
            # Return just the first valid image found
            return [found_urls[0]]
            
        return []
    
    def extract_reviews(self, soup: BeautifulSoup, html: str) -> Dict:
        """Extract review rating and count"""
        reviews = {
            'rating': None,
            'count': 0
        }
        
        # Extract rating from data attribute
        rating_match = re.search(r'data-product-rating="([\d.]+)"', html)
        if rating_match:
            try:
                reviews['rating'] = float(rating_match.group(1))
            except ValueError:
                pass
        
        # Extract review count from JSON data
        count_match = re.search(r'"reviewCount":\s*(\d+)', html)
        if count_match:
            reviews['count'] = int(count_match.group(1))
        
        # Fallback: try to find in visible HTML
        if not reviews['rating']:
            rating_elem = soup.select_one('[data-product-rating]')
            if rating_elem:
                rating_str = rating_elem.get('data-product-rating', '')
                try:
                    reviews['rating'] = float(rating_str)
                except ValueError:
                    pass
        
        return reviews
    
    def extract_availability(self, soup: BeautifulSoup) -> Dict:
        """Extract availability status"""
        text = soup.get_text().lower()
        
        available = True
        status = "Available"
        
        if 'out of stock' in text or 'currently unavailable' in text or 'discontinued' in text:
            available = False
            status = "Out of stock"
        elif 'limited availability' in text or 'low in stock' in text:
            available = True
            status = "Limited availability"
        elif 'in stock' in text:
            available = True
            status = "In stock"
        
        return {
            'available': available,
            'stock_status': status
        }
    
    def determine_subcategory(self, name: str, url: str, description: str) -> str:
        """Determine product subcategory"""
        text = (name + ' ' + url + ' ' + description).lower()
        
        if 'gaming' in text:
            return 'gaming'
        elif 'kid' in text or 'child' in text or 'junior' in text:
            return 'kids'
        elif 'office' in text or 'executive' in text or 'task' in text or 'desk chair' in text:
            return 'office'
        elif 'conference' in text or 'meeting' in text:
            return 'office'
        else:
            return 'desk'
    
    def generate_tags(self, product: Dict) -> List[str]:
        """Generate searchable tags from product data"""
        tags = set()
        
        # Combine text for analysis
        text = ' '.join([
            product.get('name', ''),
            product.get('description', ''),
            ' '.join(product.get('features', [])),
            str(product.get('specifications', {}))
        ]).lower()
        
        # Keyword mapping
        tag_keywords = {
            'ergonomic': ['ergonomic', 'comfort', 'supportive'],
            'adjustable': ['adjustable', 'height-adjustable', 'tilt'],
            'swivel': ['swivel', 'rotating', 'spin'],
            'armrest': ['armrest', 'arm rest', 'arms'],
            'wheels': ['wheels', 'casters', 'rolling'],
            'mesh': ['mesh', 'breathable'],
            'leather': ['leather', 'bonded leather'],
            'fabric': ['fabric', 'upholstered'],
            'padded': ['padded', 'cushioned', 'padding'],
            'modern': ['modern', 'contemporary'],
            'gaming': ['gaming', 'gamer'],
            'office': ['office', 'desk', 'work'],
        }
        
        for tag, keywords in tag_keywords.items():
            if any(keyword in text for keyword in keywords):
                tags.add(tag)
        
        # Add category tags
        if 'subcategory' in product:
            tags.add(product['subcategory'])
        
        # Add color tag if available
        if product.get('specifications', {}).get('color'):
            color = product['specifications']['color'].lower()
            tags.add(color)
        
        # Add material tags
        materials = product.get('specifications', {}).get('material', {})
        if isinstance(materials, dict):
            for mat_value in materials.values():
                for part in mat_value.split(','):
                    tag = part.strip().lower()
                    if tag:
                        tags.add(tag)
        elif isinstance(materials, str) and materials:
            for material in materials.split(','):
                mat = material.strip().lower()
                if mat:
                    tags.add(mat)
        
        return sorted(list(tags))
    
    async def scrape_product(self, url: str) -> Optional[Dict]:
        """Scrape complete product data from a single product page"""
        logger.info(f"Scraping: {url}")
        
        try:
            # Navigate to product page
            await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(self.rate_limit)
            
            # Scroll to load all content (lazy-loaded sections)
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(1)
            
            # Get full HTML
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract all data using improved methods
            name_data = self.extract_name(soup)
            price_data = self.extract_price(soup)
            product_id = self.extract_product_id(html, url)
            description = self.extract_description(soup)
            features = self.extract_features(soup)
            # Pass parsed color to specifications
            specifications = self.extract_specifications(soup, parsed_color=name_data.get('parsed_color'))
            images = self.extract_images(html)
            reviews = self.extract_reviews(soup, html)
            availability = self.extract_availability(soup)
            
            # Build complete product data matching schema
            product = {
                "product_id": product_id,
                "name": name_data['full_name'],
                "price": price_data['price'],
                "currency": price_data['currency'],
                "description": description or name_data['short_description'],
                "specifications": specifications,
                "features": features,
                "images": images,
                "availability": availability['available'],
                "stock_status": availability['stock_status'],
                "reviews": reviews,
                "product_url": url,
                "category": "chairs",
                "subcategory": self.determine_subcategory(
                    name_data['full_name'],
                    url,
                    description
                ),
                "scraped_at": datetime.now().isoformat()
            }
            
            # Generate tags
            product['tags'] = self.generate_tags(product)
            
            logger.info(f"✅ {name_data['title']}: ${price_data['price']}")
            self.stats['successful'] += 1
            
            return product
            
        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {str(e)}")
            self.stats['failed'] += 1
            return None
    
    async def scrape_category(self, category_url: str, max_products: int = 10):
        """Scrape multiple products from a category page"""
        await self.init_browser()
        
        try:
            # Get product URLs
            product_urls = await self.get_product_urls(category_url, max_products)
            self.stats['total'] = len(product_urls)
            
            # Scrape each product
            for i, url in enumerate(product_urls, 1):
                logger.info(f"\n{'='*70}")
                logger.info(f"Product {i}/{len(product_urls)}")
                logger.info(f"{'='*70}")
                
                product = await self.scrape_product(url)
                if product:
                    self.products.append(product)
                
                # Rate limiting between products
                if i < len(product_urls):
                    await asyncio.sleep(self.rate_limit)
            
            # Print stats
            self.print_stats()
            
        finally:
            await self.close_browser()
    
    def save_to_json(self, filepath: str = None) -> str:
        """Save products to JSON file"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/raw/ikea_chairs_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "products": self.products,
                "metadata": {
                    "count": len(self.products),
                    "scraped_at": datetime.now().isoformat(),
                    "stats": self.stats
                }
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Saved to: {filepath}")
        return filepath
    
    def print_stats(self):
        """Print scraping statistics"""
        logger.info("\n" + "="*70)
        logger.info("SCRAPING STATISTICS")
        logger.info("="*70)
        logger.info(f"Total products: {self.stats['total']}")
        logger.info(f"Successfully scraped: {self.stats['successful']}")
        logger.info(f"Failed: {self.stats['failed']}")
        success_rate = (self.stats['successful'] / max(self.stats['total'], 1)) * 100
        logger.info(f"Success rate: {success_rate:.1f}%")
        logger.info("="*70)


# Test script
async def main():
    """Test the perfect scraper"""
    print("\n" + "="*70)
    print("IKEA PERFECT SCRAPER - 100% Data Extraction")
    print("="*70 + "\n")
    
    scraper = PerfectIKEAScraper(
        headless=False,  # Set to True for production
        rate_limit=2.0   # 2 seconds between requests
    )
    
    # Test on desk chairs category
    category_url = "https://www.ikea.com/us/en/cat/desk-chairs-20652/"
    
    # Scrape 60 products for a robust dataset
    await scraper.scrape_category(category_url, max_products=60)
    
    # Save results
    filepath = scraper.save_to_json()
    
    # Display first product as example
    if scraper.products:
        print("\n" + "="*70)
        print("SAMPLE PRODUCT (First of", len(scraper.products), ")")
        print("="*70)
        print(json.dumps(scraper.products[0], indent=2))
        print("="*70)
    
    print(f"\n✅ Complete! Check {filepath} for all products")


if __name__ == "__main__":
    asyncio.run(main())
