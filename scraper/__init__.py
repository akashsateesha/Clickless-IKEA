"""
Init file for scraper module
"""

from .ikea_scraper import IKEAChairScraper
from .data_processor import DataProcessor

# Import embedding generator only if dependencies are available
try:
    from .embedding_generator import EmbeddingGenerator
    __all__ = ['IKEAChairScraper', 'DataProcessor', 'EmbeddingGenerator']
except ImportError as e:
    # Embedding dependencies not available
    __all__ = ['IKEAChairScraper', 'DataProcessor']
    EmbeddingGenerator = None
