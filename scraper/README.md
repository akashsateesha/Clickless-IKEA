# IKEA Chair Scraper

A robust, production-ready web scraper for collecting IKEA chair product data to power the IKEA Rufus conversational shopping assistant.

## 🎯 Features

- **Async Scraping**: Uses Playwright for fast, concurrent scraping
- **Rate Limiting**: Configurable delays to avoid being blocked
- **Retry Logic**: Automatic retries for failed requests
- **Comprehensive Data**: Extracts name, price, specs, images, reviews, and more
- **Data Processing**: Cleans, validates, and enriches scraped data
- **Embedding Generation**: Creates vector embeddings for RAG system
- **Modular Design**: Easy to extend and customize

## 📦 Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers

```bash
playwright install chromium
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your credentials
```

## 🚀 Quick Start

### Option 1: Run Complete Pipeline

```bash
# Scrape 20 products and generate embeddings (local model)
python scripts/run_scraper.py --max-products 20 --model local

# Scrape all products with OpenAI embeddings
python scripts/run_scraper.py --model openai
```

### Option 2: Run Individual Steps

#### Step 1: Scrape Products

```python
import asyncio
from scraper import IKEAChairScraper

async def scrape():
    scraper = IKEAChairScraper(headless=True)
    products = await scraper.scrape_all_chairs(max_products=50)
    scraper.save_to_json()

asyncio.run(scrape())
```

#### Step 2: Process Data

```python
from scraper import DataProcessor

processor = DataProcessor()
processor.load_from_json('data/raw/ikea_chairs_20231120.json')
processed = processor.process_all()
processor.save_to_json()
processor.export_for_embeddings()
```

#### Step 3: Generate Embeddings

```python
from scraper import EmbeddingGenerator

# Local model (free)
generator = EmbeddingGenerator(
    model_type="sentence-transformers",
    model_name="all-MiniLM-L6-v2"
)

# Or OpenAI (requires API key)
# generator = EmbeddingGenerator(model_type="openai")

products = generator.load_products('data/processed/ikea_chairs_cleaned.json')
embeddings = generator.generate_embeddings(products)
generator.save_embeddings()
```

## 📊 Data Structure

### Scraped Product Schema

```json
{
  "product_id": "S12345678",
  "name": "MARKUS Office chair",
  "price": 199.99,
  "currency": "USD",
  "description": "This ergonomic office chair...",
  "specifications": {
    "width": "62 cm",
    "height": "129 cm",
    "weight": "15 kg"
  },
  "features": [
    "Adjustable seat height",
    "Lumbar support",
    "Tilt function"
  ],
  "images": ["https://..."],
  "availability": true,
  "stock_status": "In stock",
  "rating": 4.5,
  "review_count": 1234,
  "materials": ["Polyester", "Steel"],
  "product_url": "https://...",
  "category": "chairs",
  "subcategory": "office",
  "tags": ["ergonomic", "adjustable", "office"],
  "scraped_at": "2023-11-20T10:30:00"
}
```

## 🔧 Configuration

### Scraper Options

```python
scraper = IKEAChairScraper(
    base_url="https://www.ikea.com/us/en",  # IKEA region
    headless=True,                           # Run browser in background
    rate_limit=2.0,                          # Seconds between requests
    max_retries=3                            # Retry attempts for failures
)
```

### Embedding Models

**Local Models** (Free, runs on your machine):
- `all-MiniLM-L6-v2`: Fast, 384 dimensions
- `all-mpnet-base-v2`: Better quality, 768 dimensions
- `paraphrase-multilingual-MiniLM-L12-v2`: Multilingual support

**OpenAI** (Requires API key, costs ~$0.0001 per 1K tokens):
- `text-embedding-ada-002`: 1536 dimensions

## 📁 Output Files

```
data/
├── raw/
│   └── ikea_chairs_20231120_103000.json       # Raw scraped data
├── processed/
│   ├── ikea_chairs_cleaned_20231120.json      # Cleaned data
│   └── ikea_chairs_for_embeddings.json        # Optimized for embeddings
└── embeddings/
    ├── ikea_chairs_embeddings_20231120.json   # Vector embeddings
    └── ikea_chairs_embeddings_metadata.json   # Searchable metadata
```

## 🔍 Advanced Usage

### Custom Selectors

If IKEA changes their website structure, update selectors in `ikea_scraper.py`:

```python
# Example: Update price selector
price_elem = soup.select_one('.new-price-class')
```

### Filter Products

```python
# Only scrape office chairs under $200
async def scrape_filtered():
    scraper = IKEAChairScraper()
    await scraper.init_browser()
    
    # Custom filtering logic
    all_urls = await scraper.get_product_urls_from_category(
        "https://www.ikea.com/us/en/cat/office-chairs-20652/"
    )
    
    for url in all_urls:
        product = await scraper.scrape_product_details(url)
        if product and product.get('price', 999) < 200:
            scraper.products.append(product)
    
    scraper.save_to_json()
    await scraper.close_browser()
```

### Batch Processing

```python
# Process multiple raw files
from pathlib import Path

processor = DataProcessor()
raw_files = Path('data/raw').glob('ikea_chairs_*.json')

all_products = []
for file in raw_files:
    processor.load_from_json(str(file))
    all_products.extend(processor.products)

processor.products = all_products
processor.process_all()
processor.save_to_json('data/processed/all_chairs_combined.json')
```

## 🐛 Troubleshooting

### Issue: Browser doesn't launch

**Solution**: Install Playwright browsers
```bash
playwright install chromium
```

### Issue: Selectors not finding elements

**Solution**: IKEA may have changed their HTML. Inspect the page and update selectors:
1. Set `headless=False` to see browser
2. Inspect HTML elements
3. Update CSS selectors in `ikea_scraper.py`

### Issue: Rate limiting / IP blocked

**Solution**: Increase rate limit or use proxies
```python
scraper = IKEAChairScraper(rate_limit=5.0)  # 5 seconds between requests
```

### Issue: OpenAI API rate limit

**Solution**: Add delays or use local model
```python
# In embedding_generator.py, increase sleep time
time.sleep(20)  # Wait 20 seconds every 50 products
```

## 📈 Performance

- **Scraping Speed**: ~5-10 seconds per product (with 2s rate limit)
- **100 products**: ~15-20 minutes
- **500 products**: ~1.5-2 hours
- **Embedding Generation** (local): ~1-2 seconds per 100 products
- **Embedding Generation** (OpenAI): ~5-10 seconds per 100 products (rate limits)

## 🔐 Privacy & Ethics

- **Respect robots.txt**: Check IKEA's robots.txt before scraping
- **Rate limiting**: Don't overwhelm IKEA's servers
- **Personal use**: This scraper is for educational/personal projects
- **API alternative**: Consider using IKEA's official API if available

## 🛠️ Development

### Running Tests

```bash
pytest tests/test_scraper.py
```

### Debugging

```python
# Enable verbose logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Run browser in non-headless mode
scraper = IKEAChairScraper(headless=False)
```

## 📝 Next Steps

After scraping:

1. **Set up Vector Database**: Load embeddings into ChromaDB/Pinecone
2. **Build RAG System**: Create semantic search with LangChain
3. **Develop Agent**: Build LangGraph conversational agent
4. **Browser Automation**: Enable cart management
5. **Deploy**: Create API and frontend

See [ARCHITECTURE.md](../ARCHITECTURE.md) for complete system design.

## 🤝 Contributing

Feel free to improve the scraper:
- Add support for more IKEA categories
- Improve data extraction accuracy
- Add support for other IKEA regions
- Optimize performance

## 📄 License

MIT License - See LICENSE file

---

Built with ❤️ for the IKEA Rufus project
