"""
Data Processor for IKEA Chair Scraper
Cleans, validates, and structures scraped data
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import re


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataProcessor:
    """
    Processes and cleans scraped IKEA chair data
    
    Features:
    - Data validation
    - Price normalization
    - Text cleaning
    - Deduplication
    - Data enrichment
    """
    
    def __init__(self):
        self.products: List[Dict] = []
        self.stats = {
            "original_count": 0,
            "cleaned_count": 0,
            "duplicates_removed": 0,
            "invalid_products": 0
        }
    
    def load_from_json(self, filepath: str) -> List[Dict]:
        """Load scraped data from JSON file"""
        logger.info(f"Loading data from {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict) and 'products' in data:
            self.products = data['products']
        elif isinstance(data, list):
            self.products = data
        else:
            raise ValueError("Invalid JSON format")
        
        self.stats["original_count"] = len(self.products)
        logger.info(f"Loaded {len(self.products)} products")
        
        return self.products
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s\-.,!?()]', '', text)
        
        return text.strip()
    
    def normalize_price(self, price: any) -> Optional[float]:
        """Normalize price to float"""
        if price is None:
            return None
        
        if isinstance(price, (int, float)):
            return float(price)
        
        if isinstance(price, str):
            # Remove currency symbols and commas
            price_str = re.sub(r'[^\d.]', '', price)
            try:
                return float(price_str)
            except ValueError:
                return None
        
        return None
    
    def extract_dimensions(self, specs: Dict) -> Dict:
        """Extract and normalize dimensions from specifications"""
        dimensions = {
            "width": None,
            "height": None,
            "depth": None,
            "unit": "cm"
        }
        
        for key, value in specs.items():
            key_lower = key.lower()
            
            if 'width' in key_lower:
                dimensions['width'] = self.extract_numeric(value)
            elif 'height' in key_lower:
                dimensions['height'] = self.extract_numeric(value)
            elif 'depth' in key_lower or 'length' in key_lower:
                dimensions['depth'] = self.extract_numeric(value)
        
        return dimensions
    
    def extract_numeric(self, text: str) -> Optional[float]:
        """Extract first numeric value from text"""
        if not text:
            return None
        
        match = re.search(r'(\d+\.?\d*)', str(text))
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
        return None
    
    def validate_product(self, product: Dict) -> bool:
        """Validate that product has required fields"""
        required_fields = ['product_id', 'name']
        
        for field in required_fields:
            if field not in product or not product[field]:
                logger.warning(f"Product missing required field: {field}")
                return False
        
        # Validate price is reasonable
        price = product.get('price')
        if price is not None:
            if not isinstance(price, (int, float)) or price < 0 or price > 10000:
                logger.warning(f"Invalid price for {product['name']}: {price}")
                return False
        
        return True
    
    def enrich_product(self, product: Dict) -> Dict:
        """Enrich product data with additional computed fields"""
        # Create search tags
        tags = self.generate_tags(product)
        product['tags'] = tags
        
        # Extract dimensions if not present
        if 'dimensions' not in product and 'specifications' in product:
            product['dimensions'] = self.extract_dimensions(product['specifications'])
        
        # Create price category
        price = product.get('price')
        if price:
            if price < 50:
                product['price_category'] = 'budget'
            elif price < 150:
                product['price_category'] = 'mid-range'
            elif price < 300:
                product['price_category'] = 'premium'
            else:
                product['price_category'] = 'luxury'
        
        # Calculate SEO score (for search ranking)
        product['seo_score'] = self.calculate_seo_score(product)
        
        return product
    
    def generate_tags(self, product: Dict) -> List[str]:
        """Generate searchable tags from product data"""
        tags = set()
        
        # Add category/subcategory
        if 'category' in product:
            tags.add(product['category'])
        if 'subcategory' in product:
            tags.add(product['subcategory'])
        
        # Extract keywords from name
        name = product.get('name', '').lower()
        for keyword in ['ergonomic', 'adjustable', 'swivel', 'leather', 'fabric', 'mesh', 
                       'gaming', 'executive', 'task', 'modern', 'vintage', 'wooden']:
            if keyword in name:
                tags.add(keyword)
        
        # Extract from description
        description = product.get('description', '').lower()
        if 'comfortable' in description or 'comfort' in description:
            tags.add('comfortable')
        if 'durable' in description:
            tags.add('durable')
        
        # Material tags
        materials = product.get('materials', [])
        for material in materials:
            material_lower = material.lower()
            if 'wood' in material_lower:
                tags.add('wooden')
            if 'metal' in material_lower:
                tags.add('metal')
            if 'fabric' in material_lower:
                tags.add('fabric')
        
        return list(tags)
    
    def calculate_seo_score(self, product: Dict) -> float:
        """Calculate SEO/search ranking score"""
        score = 0.0
        
        # Has description
        if product.get('description'):
            score += 1.0
        
        # Has images
        if product.get('images') and len(product['images']) > 0:
            score += 1.0
        
        # Has specifications
        if product.get('specifications') and len(product['specifications']) > 0:
            score += 1.0
        
        # Has features
        if product.get('features') and len(product['features']) > 0:
            score += 1.0
        
        # Has ratings
        if product.get('rating'):
            score += product['rating'] / 5.0  # 0-1 normalized
        
        # Has reviews
        if product.get('review_count', 0) > 0:
            score += min(product['review_count'] / 100, 1.0)  # Cap at 1.0
        
        return round(score, 2)
    
    def remove_duplicates(self) -> List[Dict]:
        """Remove duplicate products by product_id"""
        seen_ids = set()
        unique_products = []
        
        for product in self.products:
            product_id = product.get('product_id')
            if product_id and product_id not in seen_ids:
                seen_ids.add(product_id)
                unique_products.append(product)
            else:
                self.stats['duplicates_removed'] += 1
        
        return unique_products
    
    def process_all(self) -> List[Dict]:
        """Process all products"""
        logger.info("Starting data processing...")
        
        processed_products = []
        
        for product in self.products:
            # Validate
            if not self.validate_product(product):
                self.stats['invalid_products'] += 1
                continue
            
            # Clean text fields
            if 'name' in product:
                product['name'] = self.clean_text(product['name'])
            if 'description' in product:
                product['description'] = self.clean_text(product['description'])
            
            # Normalize price
            if 'price' in product:
                product['price'] = self.normalize_price(product['price'])
            
            # Clean features
            if 'features' in product:
                product['features'] = [self.clean_text(f) for f in product['features']]
            
            # Enrich data
            product = self.enrich_product(product)
            
            processed_products.append(product)
        
        # Remove duplicates
        processed_products = self.remove_duplicates()
        
        self.stats['cleaned_count'] = len(processed_products)
        self.products = processed_products
        
        self.print_stats()
        
        return processed_products
    
    def save_to_json(self, filepath: str = None):
        """Save processed data to JSON file"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/processed/ikea_chairs_cleaned_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "products": self.products,
                "stats": self.stats,
                "processed_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Processed data saved to {filepath}")
        return filepath
    
    def export_for_embeddings(self, filepath: str = None) -> str:
        """Export data in format optimized for embedding generation"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/processed/ikea_chairs_for_embeddings_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        embedding_data = []
        
        for product in self.products:
            embedding_data.append({
                "id": product['product_id'],
                "text": product.get('metadata', {}).get('full_text', ''),
                "metadata": {
                    "name": product['name'],
                    "price": product.get('price'),
                    "category": product.get('category'),
                    "subcategory": product.get('subcategory'),
                    "url": product.get('product_url'),
                    "rating": product.get('rating'),
                    "tags": product.get('tags', [])
                }
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(embedding_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Embedding data saved to {filepath}")
        return filepath
    
    def print_stats(self):
        """Print processing statistics"""
        logger.info("=" * 50)
        logger.info("DATA PROCESSING STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Original products: {self.stats['original_count']}")
        logger.info(f"Invalid products removed: {self.stats['invalid_products']}")
        logger.info(f"Duplicates removed: {self.stats['duplicates_removed']}")
        logger.info(f"Final cleaned products: {self.stats['cleaned_count']}")
        logger.info(f"Success rate: {self.stats['cleaned_count'] / max(self.stats['original_count'], 1) * 100:.1f}%")
        logger.info("=" * 50)


# Example usage
def main():
    """Example usage"""
    processor = DataProcessor()
    
    # Load raw data
    processor.load_from_json('data/raw/ikea_chairs_latest.json')
    
    # Process
    processed = processor.process_all()
    
    # Save cleaned data
    processor.save_to_json()
    
    # Export for embeddings
    processor.export_for_embeddings()
    
    print(f"\nProcessed {len(processed)} products")


if __name__ == "__main__":
    main()
