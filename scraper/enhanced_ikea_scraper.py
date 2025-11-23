"""
Enhanced IKEA Chair Scraper - Complete Data Extraction
Extracts all fields from the target schema
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


class EnhancedIKEAScraper:
    """Enhanced IKEA scraper that extracts complete product data"""
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.products = []
    
    async def init_browser(self):
        """Initialize browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
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
        """Extract product ID/article number"""
        soup = BeautifulSoup(html, 'lxml')
        
        # Try to find article number
        article_elem = soup.find(string=re.compile(r'Article Number', re.I))
        if article_elem:
            parent = article_elem.find_parent()
            if parent:
                # Look for number pattern like 902.891.72
                text = parent.get_text()
                match = re.search(r'\d{3}\.\d{3}\.\d{2}', text)
                if match:
                    return match.group(0).replace('.', '')
        
        # Fallback: extract from URL
        match = re.search(r'-([a-z]\d+)/?$', url, re.I)
        if match:
            return match.group(1)
        
        return url.split('/')[-1].split('-')[-1]
    
    def extract_price(self, soup: BeautifulSoup) -> Dict:
        """Extract price with better parsing"""
        price_int = soup.select_one('.pip-temp-price__integer, .pip-price__integer')
        price_dec = soup.select_one('.pip-temp-price__decimal, .pip-price__decimal')
        
        price = None
        if price_int:
            price_str = price_int.get_text(strip=True).replace('$', '').replace(',', '').strip()
            if price_dec:
                dec_str = price_dec.get_text(strip=True).replace('.', '').strip()
                price_str = f"{price_str}.{dec_str}"
            
            try:
                price = float(price_str)
            except ValueError:
                pass
        
        return {
            'price': price,
            'currency': 'USD'
        }
    
    def extract_name(self, soup: BeautifulSoup) -> Dict:
        """Extract product name and description"""
        title_elem = soup.select_one('.pip-header-section__title')
        desc_elem = soup.select_one('.pip-header-section__description')
        
        title = title_elem.get_text(strip=True) if title_elem else "Unknown"
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        
        # Full name is title + description
        full_name = f"{title} {description}".strip() if description else title
        
        return {
            'name': title,
            'full_name': full_name,
            'short_description': description
        }
    
    def extract_description(self, soup: BeautifulSoup) -> str:
        """Extract long product description"""
        # Look for main description
        desc_selectors = [
            '.pip-product-summary__description',
            '.pip-header-section__description-text',
            '[class*="product-description"]'
        ]
        
        for selector in desc_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if len(text) > 20:
                    return text
        
        # Try to find description in paragraphs
        desc_section = soup.find(string=re.compile(r'(Good to know|Product description)', re.I))
        if desc_section:
            parent = desc_section.find_parent()
            if parent:
                paragraphs = parent.find_all('p')
                if paragraphs:
                    return ' '.join([p.get_text(strip=True) for p in paragraphs])
        
        return ""
    
    def extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract key features"""
        features = []
        
        # Try key features section
        feature_section = soup.find(string=re.compile(r'Key features', re.I))
        if feature_section:
            parent = feature_section.find_parent()
            if parent:
                items = parent.find_all('li')
                for item in items:
                    text = item.get_text(strip=True)
                    if text and len(text) < 200:
                        features.append(text)
        
        # Try product details
        if not features:
            details_items = soup.select('.pip-product-details__container li')
            for item in details_items[:8]:
                text = item.get_text(strip=True)
                if text and len(text) < 200:
                    features.append(text)
        
        return features[:10]  # Limit to 10 features
    
    def extract_specifications(self, soup: BeautifulSoup) -> Dict:
        """Extract detailed specifications including materials and dimensions"""
        specs = {
            'material': None,
            'dimensions': {'height': None, 'width': None, 'depth': None},
            'weight': None,
            'color': None,
            'style': None
        }
        
        # Extract dimensions
        measurement_section = soup.find('div', id=re.compile(r'SEC_product-information-dimensions'))
        if measurement_section:
            measurement_items = measurement_section.find_all(['dt', 'dd', 'li'])
            
            current_label = None
            for item in measurement_items:
                text = item.get_text(strip=True)
                
                if item.name in ['dt', 'span']:
                    current_label = text.lower()
                else:
                    # Extract numeric value
                    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:"|in|cm)', text)
                    if match:
                        value = float(match.group(1))
                        
                        if current_label:
                            if 'width' in current_label:
                                specs['dimensions']['width'] = value
                            elif 'height' in current_label or 'max. height' in current_label:
                                specs['dimensions']['height'] = value
                            elif 'depth' in current_label:
                                specs['dimensions']['depth'] = value
                            elif 'weight' in current_label:
                                specs['weight'] = value
        
        # Extract materials
        material_section = soup.find('div', id=re.compile(r'SEC_product-information-text'))
        if material_section:
            material_text = material_section.get_text()
            
            # Look for material patterns
            materials = []
            material_keywords = ['steel', 'wood', 'fabric', 'leather', 'plastic', 'polyester', 
                               'polypropylene', 'polyethylene', 'metal', 'foam']
            
            for keyword in material_keywords:
                if keyword in material_text.lower():
                    materials.append(keyword.capitalize())
            
            if materials:
                specs['material'] = ', '.join(list(set(materials))[:3])
        
        # Extract color from name/description
        color_elem = soup.select_one('.pip-header-section__description')
        if color_elem:
            color_text = color_elem.get_text(strip=True)
            # Common IKEA colors
            colors = ['black', 'white', 'gray', 'grey', 'blue', 'red', 'green', 
                     'brown', 'beige', 'yellow', 'orange', 'pink']
            for color in colors:
                if color in color_text.lower():
                    specs['color'] = color.capitalize()
                    break
        
        return specs
    
    def extract_images(self, html: str) -> List[str]:
        """Extract product images"""
        images = []
        
        # Try to find images in data-hydration-props
        match = re.search(r'"productGallery":\s*({[^}]+})', html)
        if match:
            try:
                # Look for image URLs in the JSON
                urls = re.findall(r'https://[^"]+\.(?:jpg|jpeg|png|webp)', html)
                images = list(set(urls))[:5]  # Limit to 5 unique images
            except:
                pass
        
        # Fallback: find images in img tags
        if not images:
            soup = BeautifulSoup(html, 'lxml')
            img_elements = soup.select('.pip-media-grid__thumbnail img, .pip-aspect-ratio-image img')
            for img in img_elements[:5]:
                src = img.get('src') or img.get('data-src')
                if src and 'http' in src:
                    images.append(src)
        
        return images
    
    def extract_reviews(self, soup: BeautifulSoup, html: str) -> Dict:
        """Extract review data"""
        reviews = {
            'rating': None,
            'count': 0
        }
        
        # Try to find rating in data attributes
        rating_match = re.search(r'data-product-rating="([\d.]+)"', html)
        if rating_match:
            try:
                reviews['rating'] = float(rating_match.group(1))
            except:
                pass
        
        # Try to find review count
        count_match = re.search(r'"reviewCount":\s*(\d+)', html)
        if count_match:
            reviews['count'] = int(count_match.group(1))
        
        # Fallback: look in HTML
        if not reviews['rating']:
            rating_elem = soup.select_one('[class*="rating"]')
            if rating_elem:
                rating_text = rating_elem.get('aria-label', '')
                match = re.search(r'([\d.]+)\s*out of', rating_text)
                if match:
                    reviews['rating'] = float(match.group(1))
        
        return reviews
    
    def extract_availability(self, soup: BeautifulSoup) -> Dict:
        """Extract availability information"""
        avail_text = soup.get_text().lower()
        
        available = True
        status = "Available"
        
        if 'out of stock' in avail_text or 'currently unavailable' in avail_text:
            available = False
            status = "Out of stock"
        elif 'limited' in avail_text:
            status = "Limited availability"
        elif 'in stock' in avail_text:
            status = "In stock"
        
        return {
            'available': available,
            'stock_status': status
        }
    
    def determine_subcategory(self, name: str, url: str) -> str:
        """Determine product subcategory"""
        text = name.lower() + ' ' + url.lower()
        
        if 'gaming' in text:
            return 'gaming'
        elif 'office' in text or 'desk' in text or 'task' in text:
            return 'office'
        elif 'kid' in text or 'child' in text:
            return 'kids'
        elif 'dining' in text:
            return 'dining'
        else:
            return 'desk'
    
    def generate_tags(self, product: Dict) -> List[str]:
        """Generate searchable tags"""
        tags = set()
        
        text = (product.get('name', '') + ' ' + 
                product.get('description', '') + ' ' +
                ' '.join(product.get('features', []))).lower()
        
        keywords = {
            'ergonomic': ['ergonomic', 'comfort'],
            'adjustable': ['adjustable', 'height-adjustable'],
            'swivel': ['swivel', 'rotating'],
            'armrest': ['armrest', 'arm rest'],
            'wheels': ['wheels', 'casters'],
            'mesh': ['mesh'],
            'leather': ['leather'],
            'fabric': ['fabric'],
            'gaming': ['gaming'],
            'executive': ['executive'],
            'modern': ['modern', 'contemporary'],
            'classic': ['classic', 'traditional'],
        }
        
        for tag, patterns in keywords.items():
            if any(pattern in text for pattern in patterns):
                tags.add(tag)
        
        # Add category
        if 'subcategory' in product:
            tags.add(product['subcategory'])
        
        return list(tags)
    
    async def scrape_product(self, url: str) -> Optional[Dict]:
        """Scrape complete product data"""
        logger.info(f"Scraping: {url}")
        
        try:
            await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            
            # Scroll to load all content
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(2)
            
            # Get HTML
            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract all data
            name_data = self.extract_name(soup)
            price_data = self.extract_price(soup)
            product_id = self.extract_product_id(html, url)
            description = self.extract_description(soup)
            features = self.extract_features(soup)
            specifications = self.extract_specifications(soup)
            images = self.extract_images(html)
            reviews = self.extract_reviews(soup, html)
            availability = self.extract_availability(soup)
            
            # Build complete product data
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
                "subcategory": self.determine_subcategory(name_data['full_name'], url),
                "scraped_at": datetime.now().isoformat()
            }
            
            # Add tags
            product['tags'] = self.generate_tags(product)
            
            logger.info(f"✅ Successfully scraped: {name_data['name']} (${price_data['price']})")
            return product
            
        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {str(e)}")
            return None
    
    async def scrape_category(self, category_url: str, max_products: int = 10):
        """Scrape multiple products from category"""
        await self.init_browser()
        
        try:
            # Get product URLs
            product_urls = await self.get_product_urls(category_url, max_products)
            
            # Scrape each product
            for i, url in enumerate(product_urls, 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"Product {i}/{len(product_urls)}")
                logger.info(f"{'='*60}")
                
                product = await self.scrape_product(url)
                if product:
                    self.products.append(product)
                
                # Small delay between products
                await asyncio.sleep(2)
            
            logger.info(f"\n✅ Scraped {len(self.products)} products successfully")
            
        finally:
            await self.close_browser()
    
    def save_to_json(self, filepath: str = None):
        """Save products to JSON"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/raw/ikea_desk_chairs_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "products": self.products,
                "count": len(self.products),
                "scraped_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Saved to: {filepath}")
        return filepath


# Test script
async def main():
    """Test the enhanced scraper"""
    scraper = EnhancedIKEAScraper(headless=False)
    
    # Scrape desk chairs
    category_url = "https://www.ikea.com/us/en/cat/desk-chairs-20652/"
    
    await scraper.scrape_category(category_url, max_products=3)
    
    filepath = scraper.save_to_json()
    
    # Print first product as example
    if scraper.products:
        print("\n" + "="*60)
        print("SAMPLE SCRAPED PRODUCT:")
        print("="*60)
        print(json.dumps(scraper.products[0], indent=2))
        print("="*60)
        print(f"\nTotal products: {len(scraper.products)}")
        print(f"Saved to: {filepath}")


if __name__ == "__main__":
    asyncio.run(main())
