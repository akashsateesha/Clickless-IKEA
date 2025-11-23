"""
Product Resolver - LLM-based intelligent product matching

This module uses Gemini LLM to intelligently match user's natural language
product references to actual products from the catalog or cart, eliminating
the need for hardcoded ordinal references.
"""

import json
import logging
from typing import List, Dict, Optional
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)


def call_gemini_for_product_matching(prompt: str) -> str:
    """Helper to call Gemini API for product matching."""
    import os
    import requests
    
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        logger.error("GOOGLE_API_KEY not found in environment variables")
        return ""
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        logger.error(f"Gemini API Error in product matching: {e}")
        return ""


def resolve_product_reference(
    query: str,
    available_products: List[Dict],
    conversation_history: Optional[List] = None
) -> Dict:
    """
    Use LLM to intelligently match user's product reference to actual products.
    
    Args:
        query: User's natural language query (e.g., "add the modern office chair")
        available_products: List of product dicts with metadata
        conversation_history: Recent conversation messages for context
        
    Returns:
        {
            "matched_products": [list of matched products],
            "confidence": float (0.0 to 1.0),
            "reasoning": str,
            "needs_clarification": bool
        }
    """
    if not available_products:
        return {
            "matched_products": [],
            "confidence": 0.0,
            "reasoning": "No products available to match",
            "needs_clarification": True
        }
    
    # Build product list for LLM
    product_descriptions = []
    for i, product in enumerate(available_products):
        meta = product.get('metadata', {})
        doc = product.get('document', '')
        
        name = meta.get('name', 'Unknown')
        price = meta.get('price', 'N/A')
        
        # Truncate document for context
        description = doc[:200] if doc else "No description"
        
        product_descriptions.append(
            f"{i+1}. {name} (${price})\n   Description: {description}"
        )
    
    products_text = "\n\n".join(product_descriptions)
    
    # Build conversation context
    history_text = ""
    if conversation_history:
        recent_messages = conversation_history[-4:]  # Last 4 messages
        history_text = "\n".join([
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content[:100]}"
            for m in recent_messages
        ])
    
    # Construct LLM prompt for product matching
    history_part = f"RECENT CONVERSATION:\n{history_text}\n\n" if history_text else ""
    
    matching_prompt = f"""You are a product matching expert. Your job is to identify which product(s) the user is referring to based on their query.

AVAILABLE PRODUCTS:
{products_text}

{history_part}USER'S QUERY: "{query}"

Analyze the query and determine which product(s) the user is most likely referring to. Consider:
- Explicit product names or descriptions
- Product attributes (color, features, style, price)
- Ordinal references (first, second, third, etc.)
- Pronouns (it, that, this) - usually refers to the first or most recent product
- Semantic similarity to product descriptions

Respond in JSON format:
{{
  "matched_indices": [<0-based indices of matched products>],
  "confidence": <0.0 to 1.0>,
  "reasoning": "<brief explanation of why you chose these products>",
  "needs_clarification": <true if ambiguous, false if confident>
}}

CONFIDENCE GUIDELINES:
- 0.9-1.0: Exact name match or unambiguous ordinal reference
- 0.7-0.9: Strong semantic match or clear description
- 0.5-0.7: Moderate match, some ambiguity
- 0.0-0.5: Weak match or very ambiguous

Return ONLY valid JSON, no markdown formatting."""

    response = call_gemini_for_product_matching(matching_prompt)
    
    # Clean up response if it contains markdown code blocks
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0].strip()
    elif "```" in response:
        response = response.split("```")[1].split("```")[0].strip()
    
    try:
        result = json.loads(response)
        
        # Extract matched products
        matched_indices = result.get('matched_indices', [])
        matched_products = [
            available_products[i] 
            for i in matched_indices 
            if 0 <= i < len(available_products)
        ]
        
        return {
            "matched_products": matched_products,
            "confidence": float(result.get('confidence', 0.0)),
            "reasoning": result.get('reasoning', ''),
            "needs_clarification": result.get('needs_clarification', False)
        }
        
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error(f"Failed to parse LLM response for product matching: {e}")
        logger.debug(f"Raw response: {response}")
        
        # Fallback: try simple keyword matching
        return fallback_keyword_matching(query, available_products)


def fallback_keyword_matching(query: str, available_products: List[Dict]) -> Dict:
    """
    Fallback method using simple keyword matching when LLM fails.
    
    Args:
        query: User's query
        available_products: List of products
        
    Returns:
        Same format as resolve_product_reference
    """
    query_lower = query.lower()
    matches = []
    
    for i, product in enumerate(available_products):
        meta = product.get('metadata', {})
        doc = product.get('document', '').lower()
        name = meta.get('name', '').lower()
        
        # Simple keyword overlap
        query_words = set(query_lower.split())
        name_words = set(name.split())
        doc_words = set(doc.split())
        
        overlap_name = len(query_words & name_words)
        overlap_doc = len(query_words & doc_words)
        
        if overlap_name > 0 or overlap_doc > 2:
            matches.append((i, overlap_name + overlap_doc * 0.5))
    
    if matches:
        # Sort by score
        matches.sort(key=lambda x: x[1], reverse=True)
        best_match_idx = matches[0][0]
        confidence = min(0.6, matches[0][1] / 10)  # Cap at 0.6 for fallback
        
        return {
            "matched_products": [available_products[best_match_idx]],
            "confidence": confidence,
            "reasoning": "Fallback keyword matching",
            "needs_clarification": confidence < 0.5
        }
    
    return {
        "matched_products": [],
        "confidence": 0.0,
        "reasoning": "No matches found",
        "needs_clarification": True
    }


def generate_clarification_message(
    query: str,
    resolution_result: Dict,
    available_products: List[Dict]
) -> str:
    """
    Generate a helpful clarification message when product matching is ambiguous.
    
    Args:
        query: Original user query
        resolution_result: Result from resolve_product_reference
        available_products: List of available products
        
    Returns:
        HTML formatted clarification message
    """
    matched = resolution_result.get('matched_products', [])
    
    if not matched and not available_products:
        return "I don't have any products to choose from. Could you search for products first?"
    
    if not matched:
        # No matches found - show all available
        return f"""I'm not sure which product you're referring to with "{query}". Here are the available options:

<ul style="list-style: none; padding: 0;">
{_format_product_list(available_products[:5])}
</ul>

Please specify which one you'd like by being more specific (e.g., mention the product name, color, or say "the first one")."""
    
    elif len(matched) > 1:
        # Multiple matches - ask to clarify
        return f"""I found multiple products that might match "{query}":

<ul style="list-style: none; padding: 0;">
{_format_product_list(matched)}
</ul>

Which one would you like? You can say "the first one" or be more specific."""
    
    else:
        # Should not reach here as this function is for clarification
        return "Could you please clarify which product you mean?"


def _format_product_list(products: List[Dict]) -> str:
    """Format products as HTML list items."""
    items = []
    for i, product in enumerate(products):
        meta = product.get('metadata', {})
        name = meta.get('name', 'Unknown')
        price = meta.get('price', 'N/A')
        items.append(
            f'<li style="padding: 8px; margin: 4px 0; background: #f5f5f5; border-radius: 6px;">'
            f'{i+1}. {name} - ${price}</li>'
        )
    return '\n'.join(items)
