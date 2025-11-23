#!/usr/bin/env python3
"""
Master script to run the complete IKEA scraping pipeline:
1. Scrape IKEA chairs
2. Process and clean data
3. Generate embeddings

Usage:
    python scripts/run_scraper.py --max-products 50 --model local
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper.ikea_scraper import IKEAChairScraper
from scraper.data_processor import DataProcessor
from scraper.embedding_generator import EmbeddingGenerator


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='IKEA Chair Scraper Pipeline')
    
    parser.add_argument(
        '--max-products',
        type=int,
        default=None,
        help='Maximum number of products to scrape (default: all)'
    )
    
    parser.add_argument(
        '--headless',
        type=bool,
        default=True,
        help='Run browser in headless mode (default: True)'
    )
    
    parser.add_argument(
        '--model',
        type=str,
        choices=['local', 'openai'],
        default='local',
        help='Embedding model to use (default: local)'
    )
    
    parser.add_argument(
        '--skip-scrape',
        action='store_true',
        help='Skip scraping and use existing data'
    )
    
    parser.add_argument(
        '--skip-embeddings',
        action='store_true',
        help='Skip embedding generation'
    )
    
    parser.add_argument(
        '--raw-file',
        type=str,
        default=None,
        help='Path to existing raw data file (if --skip-scrape)'
    )
    
    return parser.parse_args()


async def run_scraper(args):
    """Run the scraper"""
    print("=" * 60)
    print("STEP 1: SCRAPING IKEA CHAIRS")
    print("=" * 60)
    
    scraper = IKEAChairScraper(
        headless=args.headless,
        rate_limit=2.0
    )
    
    products = await scraper.scrape_all_chairs(max_products=args.max_products)
    
    raw_filepath = scraper.save_to_json()
    
    print(f"\n✅ Scraped {len(products)} products")
    print(f"📁 Raw data saved to: {raw_filepath}")
    
    return raw_filepath


def run_processor(raw_filepath):
    """Run the data processor"""
    print("\n" + "=" * 60)
    print("STEP 2: PROCESSING & CLEANING DATA")
    print("=" * 60)
    
    processor = DataProcessor()
    processor.load_from_json(raw_filepath)
    
    processed = processor.process_all()
    
    cleaned_filepath = processor.save_to_json()
    embedding_filepath = processor.export_for_embeddings()
    
    print(f"\n✅ Processed {len(processed)} products")
    print(f"📁 Cleaned data saved to: {cleaned_filepath}")
    print(f"📁 Embedding data saved to: {embedding_filepath}")
    
    return cleaned_filepath


def run_embedding_generator(cleaned_filepath, model_type):
    """Run the embedding generator"""
    print("\n" + "=" * 60)
    print("STEP 3: GENERATING EMBEDDINGS")
    print("=" * 60)
    
    model_config = {
        'local': {
            'model_type': 'sentence-transformers',
            'model_name': 'all-MiniLM-L6-v2'
        },
        'openai': {
            'model_type': 'openai',
            'model_name': 'text-embedding-ada-002'
        }
    }
    
    config = model_config[model_type]
    
    generator = EmbeddingGenerator(
        model_type=config['model_type'],
        model_name=config['model_name']
    )
    
    products = generator.load_products(cleaned_filepath)
    embeddings = generator.generate_embeddings(products)
    
    embedding_filepath = generator.save_embeddings()
    
    stats = generator.get_embedding_stats()
    
    print(f"\n✅ Generated {len(embeddings)} embeddings")
    print(f"📁 Embeddings saved to: {embedding_filepath}")
    print("\nEmbedding Statistics:")
    for key, value in stats.items():
        print(f"  • {key}: {value}")
    
    return embedding_filepath


async def main():
    """Main pipeline"""
    args = parse_args()
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║         IKEA CHAIR SCRAPER PIPELINE                      ║
    ║         Building Data for IKEA Rufus Chatbot             ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    try:
        # Step 1: Scrape data
        if args.skip_scrape:
            if not args.raw_file:
                print("❌ Error: --raw-file required when using --skip-scrape")
                sys.exit(1)
            raw_filepath = args.raw_file
            print(f"⏭️  Skipping scraping, using: {raw_filepath}")
        else:
            raw_filepath = await run_scraper(args)
        
        # Step 2: Process data
        cleaned_filepath = run_processor(raw_filepath)
        
        # Step 3: Generate embeddings
        if args.skip_embeddings:
            print("\n⏭️  Skipping embedding generation")
        else:
            embedding_filepath = run_embedding_generator(cleaned_filepath, args.model)
        
        # Final summary
        print("\n" + "=" * 60)
        print("🎉 PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Set up ChromaDB vector store")
        print("  2. Load embeddings into vector DB")
        print("  3. Build LangGraph agent")
        print("  4. Test conversational interface")
        print("\nHappy building! 🚀")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
