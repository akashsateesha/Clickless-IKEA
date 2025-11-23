import os
import json
import logging
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RAGManager:
    """
    Manages the RAG system: Indexing products and retrieving them.
    Uses ChromaDB for vector storage and OpenAI for embeddings.
    """
    
    def __init__(self, collection_name: str = "ikea_products", persist_dir: str = "data/chroma_db"):
        self.collection_name = collection_name
        self.persist_dir = persist_dir
        
        # Initialize OpenAI Client (expects OPENAI_API_KEY in env)
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("⚠️ OPENAI_API_KEY not found in environment variables. Embeddings may fail.")
        
        # Initialize ChromaDB Client
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Initialize ChromaDB Client
        self.client = chromadb.PersistentClient(path=persist_dir)
        
        # Use ChromaDB Default Embedding Function (ONNX-based, no Keras/TF dependency)
        try:
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            logger.info("✅ Using ChromaDB Default embeddings (ONNX)")
        except Exception as e:
            logger.error(f"❌ Failed to load DefaultEmbeddingFunction: {e}")
            raise
        
        # Get or Create Collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "IKEA Product Catalog"}
        )
        
        logger.info(f"✅ RAG Manager initialized. Collection: {collection_name}")

    def prepare_product_text(self, product: Dict) -> str:
        """
        Creates a rich semantic text representation of the product for embedding.
        """
        # Extract key info
        name = product.get('name', 'Unknown')
        price = product.get('price', 0)
        desc = product.get('description', '')
        color = product.get('specifications', {}).get('color', 'Unknown')
        style = product.get('specifications', {}).get('style', '')
        category = product.get('subcategory', 'chair')
        
        # Format features
        features = ", ".join(product.get('features', [])[:5])
        
        # Format materials
        materials_dict = product.get('specifications', {}).get('material', {})
        materials_str = ""
        if isinstance(materials_dict, dict):
            materials_str = ", ".join([f"{k}: {v}" for k, v in materials_dict.items()])
        elif isinstance(materials_dict, str):
            materials_str = materials_dict
            
        # Format dimensions
        dims = product.get('specifications', {}).get('dimensions', {})
        dims_str = ""
        if isinstance(dims, dict):
            dims_str = ", ".join([f"{k}: {v}" for k, v in dims.items()])

        # Construct semantic document
        text = f"""
        Product: {name}
        Category: {category}
        Price: ${price}
        Color: {color}
        Style: {style}
        
        Description:
        {desc}
        
        Dimensions:
        {dims_str}
        
        Key Features:
        {features}
        
        Materials:
        {materials_str}
        """.strip()
        
        return text

    def ingest_data(self, json_path: str):
        """
        Loads product data from JSON and indexes it into ChromaDB.
        """
        logger.info(f"📥 Loading data from {json_path}...")
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                products = data.get('products', [])
            
            if not products:
                logger.warning("No products found in JSON file.")
                return
            
            ids = []
            documents = []
            metadatas = []
            seen_ids = set()
            
            for product in products:
                pid = product.get('product_id')
                if not pid:
                    continue
                
                # Deduplicate within this batch
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                
                # Create semantic text
                text = self.prepare_product_text(product)
                
                # Prepare dimensions string for metadata
                dims = product.get('specifications', {}).get('dimensions', {})
                dims_str = ""
                if isinstance(dims, dict):
                    dims_str = ", ".join([f"{k}: {v}" for k, v in dims.items()])
                
                # Create metadata (store essential fields for retrieval display)
                # ChromaDB metadata values must be str, int, float, or bool
                meta = {
                    "product_id": pid,
                    "name": product.get('name', ''),
                    "price": float(product.get('price', 0)),
                    "url": product.get('product_url', ''),
                    "image_url": product.get('images', [''])[0] if product.get('images') else '',
                    "category": product.get('category', ''),
                    "subcategory": product.get('subcategory', ''),
                    "color": product.get('specifications', {}).get('color', ''),
                    "rating": float(product.get('reviews', {}).get('rating', 0) or 0),
                    "dimensions": dims_str
                }
                
                ids.append(pid)
                documents.append(text)
                metadatas.append(meta)
            
            # Batch upsert (Chroma handles batching, but good to be safe)
            batch_size = 100
            total = len(ids)
            
            for i in range(0, total, batch_size):
                end = min(i + batch_size, total)
                self.collection.upsert(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end]
                )
                logger.info(f"Indexed batch {i}-{end}/{total}")
                
            logger.info(f"✅ Successfully indexed {total} products!")
            
        except Exception as e:
            logger.error(f"❌ Error ingesting data: {str(e)}")
            raise

    def search(self, query: str, k: int = 3) -> List[Dict]:
        """
        Search for products matching the query.
        """
        logger.info(f"🔍 Searching for: '{query}'")
        
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )
        
        # Format results
        formatted_results = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                item = {
                    "id": results['ids'][0][i],
                    "score": results['distances'][0][i] if 'distances' in results else 0,
                    "metadata": results['metadatas'][0][i],
                    "document": results['documents'][0][i]
                }
                formatted_results.append(item)
        
        return formatted_results

# Test execution
if __name__ == "__main__":
    # Example usage
    rag = RAGManager()
    
    # Check if we have data to ingest
    import glob
    files = glob.glob("data/raw/ikea_chairs_*.json")
    if files:
        latest_file = max(files, key=os.path.getctime)
        print(f"Found latest data file: {latest_file}")
        rag.ingest_data(latest_file)
        
        # Test search
        print("\nTesting Search: 'ergonomic office chair'")
        results = rag.search("ergonomic office chair", k=2)
        for r in results:
            print(f"\nProduct: {r['metadata']['name']}")
            print(f"Price: ${r['metadata']['price']}")
            print(f"Score: {r['score']}")
    else:
        print("No data files found. Run scraper first.")
