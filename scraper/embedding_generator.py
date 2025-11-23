"""
Embedding Generator for IKEA Chair Products
Generates vector embeddings for RAG system
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available. Install with: pip install sentence-transformers")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("openai not available. Install with: pip install openai")

import os
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class EmbeddingGenerator:
    """
    Generates embeddings for product data
    
    Supports:
    - OpenAI embeddings (text-embedding-ada-002)
    - Sentence Transformers (local models)
    """
    
    def __init__(
        self,
        model_type: str = "sentence-transformers",  # or "openai"
        model_name: str = "all-MiniLM-L6-v2"  # for sentence-transformers
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.embeddings: List[Dict] = []
        
        if model_type == "sentence-transformers":
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError("sentence-transformers not installed")
            
            logger.info(f"Loading sentence-transformers model: {model_name}")
            self.model = SentenceTransformer(model_name)
            logger.info("Model loaded successfully")
            
        elif model_type == "openai":
            if not OPENAI_AVAILABLE:
                raise ImportError("openai package not installed")
            
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            
            self.client = openai.OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized")
        
        else:
            raise ValueError(f"Unknown model_type: {model_type}")
    
    def load_products(self, filepath: str) -> List[Dict]:
        """Load product data from JSON"""
        logger.info(f"Loading products from {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            products = data
        elif isinstance(data, dict):
            products = data.get('products', [])
        else:
            raise ValueError("Invalid JSON format")
        
        logger.info(f"Loaded {len(products)} products")
        return products
    
    def create_embedding_text(self, product: Dict) -> str:
        """
        Create optimized text for embedding
        Combines all relevant product information
        """
        parts = []
        
        # Product name (most important)
        if 'name' in product:
            parts.append(f"Product: {product['name']}")
        
        # Description
        if 'description' in product:
            parts.append(f"Description: {product['description']}")
        
        # Category
        if 'subcategory' in product:
            parts.append(f"Type: {product['subcategory']} chair")
        
        # Price (for range queries)
        if 'price' in product and product['price']:
            parts.append(f"Price: ${product['price']}")
        
        # Features
        if 'features' in product and product['features']:
            features_str = "; ".join(product['features'][:5])  # Top 5 features
            parts.append(f"Features: {features_str}")
        
        # Specifications
        if 'specifications' in product:
            specs = product['specifications']
            spec_parts = []
            for key, value in list(specs.items())[:5]:  # Top 5 specs
                spec_parts.append(f"{key}: {value}")
            if spec_parts:
                parts.append(f"Specifications: {'; '.join(spec_parts)}")
        
        # Materials
        if 'materials' in product and product['materials']:
            materials_str = ", ".join(product['materials'][:3])
            parts.append(f"Materials: {materials_str}")
        
        # Tags
        if 'tags' in product and product['tags']:
            tags_str = ", ".join(product['tags'][:5])
            parts.append(f"Tags: {tags_str}")
        
        # Combine all parts
        embedding_text = " | ".join(parts)
        
        # Truncate if too long (models have token limits)
        max_length = 8000  # Conservative limit
        if len(embedding_text) > max_length:
            embedding_text = embedding_text[:max_length]
        
        return embedding_text
    
    def generate_embedding_openai(self, text: str) -> List[float]:
        """Generate embedding using OpenAI"""
        try:
            response = self.client.embeddings.create(
                model="text-embedding-ada-002",
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating OpenAI embedding: {str(e)}")
            return None
    
    def generate_embedding_local(self, text: str) -> List[float]:
        """Generate embedding using sentence-transformers"""
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Error generating local embedding: {str(e)}")
            return None
    
    def generate_embeddings(self, products: List[Dict], batch_size: int = 32) -> List[Dict]:
        """
        Generate embeddings for all products
        
        Args:
            products: List of product dictionaries
            batch_size: Batch size for processing (only for local models)
        
        Returns:
            List of embedding dictionaries
        """
        logger.info(f"Generating embeddings for {len(products)} products...")
        
        embeddings = []
        
        if self.model_type == "sentence-transformers":
            # Batch processing for local models
            texts = [self.create_embedding_text(p) for p in products]
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
                
                try:
                    batch_embeddings = self.model.encode(batch, convert_to_numpy=True, show_progress_bar=True)
                    
                    for j, embedding in enumerate(batch_embeddings):
                        product = products[i+j]
                        embeddings.append({
                            "id": product.get('product_id', f"product_{i+j}"),
                            "embedding": embedding.tolist(),
                            "metadata": {
                                "name": product.get('name'),
                                "price": product.get('price'),
                                "category": product.get('category'),
                                "subcategory": product.get('subcategory'),
                                "url": product.get('product_url'),
                                "rating": product.get('rating'),
                                "tags": product.get('tags', []),
                                "text": self.create_embedding_text(product)
                            }
                        })
                except Exception as e:
                    logger.error(f"Error processing batch: {str(e)}")
        
        elif self.model_type == "openai":
            # Sequential processing for OpenAI (to manage rate limits)
            for i, product in enumerate(products):
                logger.info(f"Processing product {i+1}/{len(products)}: {product.get('name')}")
                
                text = self.create_embedding_text(product)
                embedding = self.generate_embedding_openai(text)
                
                if embedding:
                    embeddings.append({
                        "id": product.get('product_id', f"product_{i}"),
                        "embedding": embedding,
                        "metadata": {
                            "name": product.get('name'),
                            "price": product.get('price'),
                            "category": product.get('category'),
                            "subcategory": product.get('subcategory'),
                            "url": product.get('product_url'),
                            "rating": product.get('rating'),
                            "tags": product.get('tags', []),
                            "text": text
                        }
                    })
                
                # Rate limiting for OpenAI
                if (i + 1) % 50 == 0:
                    logger.info("Pausing for rate limiting...")
                    import time
                    time.sleep(10)
        
        self.embeddings = embeddings
        logger.info(f"Generated {len(embeddings)} embeddings")
        
        return embeddings
    
    def save_embeddings(self, filepath: str = None) -> str:
        """Save embeddings to JSON file"""
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"data/embeddings/ikea_chairs_embeddings_{timestamp}.json"
        
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        # Save embeddings
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "embeddings": self.embeddings,
                "model_type": self.model_type,
                "model_name": self.model_name,
                "embedding_dim": len(self.embeddings[0]['embedding']) if self.embeddings else 0,
                "count": len(self.embeddings),
                "generated_at": datetime.now().isoformat()
            }, f, indent=2)
        
        logger.info(f"Embeddings saved to {filepath}")
        
        # Also save metadata separately for easier access
        metadata_filepath = filepath.replace('.json', '_metadata.json')
        metadata = [
            {
                "id": emb['id'],
                "metadata": emb['metadata']
            }
            for emb in self.embeddings
        ]
        
        with open(metadata_filepath, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Metadata saved to {metadata_filepath}")
        
        return filepath
    
    def get_embedding_stats(self) -> Dict:
        """Get statistics about embeddings"""
        if not self.embeddings:
            return {}
        
        return {
            "total_embeddings": len(self.embeddings),
            "embedding_dimension": len(self.embeddings[0]['embedding']),
            "model_type": self.model_type,
            "model_name": self.model_name,
            "avg_text_length": sum(len(e['metadata']['text']) for e in self.embeddings) / len(self.embeddings)
        }


# Example usage
def main():
    """Example usage"""
    # Option 1: Use local model (free, runs on your machine)
    generator = EmbeddingGenerator(
        model_type="sentence-transformers",
        model_name="all-MiniLM-L6-v2"  # Fast and good quality
        # Other options: "all-mpnet-base-v2" (better quality, slower)
    )
    
    # Option 2: Use OpenAI (requires API key, costs money)
    # generator = EmbeddingGenerator(model_type="openai")
    
    # Load processed product data
    products = generator.load_products('data/processed/ikea_chairs_cleaned_latest.json')
    
    # Generate embeddings
    embeddings = generator.generate_embeddings(products)
    
    # Save embeddings
    filepath = generator.save_embeddings()
    
    # Print stats
    stats = generator.get_embedding_stats()
    print("\nEmbedding Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\nEmbeddings saved to: {filepath}")


if __name__ == "__main__":
    main()
