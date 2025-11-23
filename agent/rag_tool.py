from langchain_core.tools import tool
from scraper.rag_manager import RAGManager

# Initialize RAG Manager (singleton-ish)
rag = RAGManager()

@tool
def search_ikea(query: str):
    """
    Search for IKEA products based on user query.
    Use this tool when the user asks for product recommendations, prices, or descriptions.
    Input should be a descriptive search string (e.g., "white ergonomic desk chair under $200").
    """
    # Perform search
    results = rag.search(query, k=5)
    
    if not results:
        return "No matching products found in the catalog."
    
    # Format output for the LLM
    response = "Found the following products:\n\n"
    for r in results:
        meta = r['metadata']
        doc = r['document']
        
        # Extract key details from document text to give LLM context
        # The document text already contains Name, Price, Description, Features
        response += f"PRODUCT ID: {meta['product_id']}\n"
        response += f"{doc}\n"
        response += f"Image: {meta['image_url']}\n"
        response += "-" * 30 + "\n"
        
    return response
