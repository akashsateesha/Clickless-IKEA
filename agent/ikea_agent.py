import os
import requests
import json
from typing import Annotated
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
import google.generativeai as genai

from dotenv import load_dotenv
from agent.rag_tool import rag
import asyncio

import nest_asyncio
nest_asyncio.apply()

# Load environment variables
load_dotenv(override=True)

# Define Agent State (Updated/Replaced)
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    last_shown_products: list  # Track products shown for follow-up context
    cart_items: list  # Local cart state
    pending_clarification_context: dict  # Track clarification flow state
    last_mentioned_product_index: int  # Track which product is currently being discussed

def call_gemini_api(prompt: str) -> str:
    """Helper to call Gemini API directly."""
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in environment variables")
        return ""
        
    # Print first/last chars for debugging (safe)
    print(f"DEBUG: Using API Key: {api_key[:4]}...{api_key[-4:]}")
    
    # Revert to preview model as requested
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
        print(f"Gemini API Error: {e}")
        return ""

def analyze_user_intent(query: str, conversation_history: list, last_products: list, pending_search_context: dict = None, cart_items: list = None) -> dict:
    """Use LLM to analyze user intent and extract structured information."""
    
    # Default empty cart if not provided
    if cart_items is None:
        cart_items = []
    
    # Build product context
    product_list = ""
    if last_products:
        product_list = "\n".join([
            f"{i+1}. {p.get('metadata', {}).get('name', 'Unknown')} - ${p.get('metadata', {}).get('price', 'N/A')}"
            for i, p in enumerate(last_products[:10])  # Increased to 10
        ])
    
    # Format conversation history
    history_text = "\n".join([
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
        for m in conversation_history[-6:]
    ])
    
    # Add pending context info
    pending_context_info = ""
    if pending_search_context:
        pending_context_info = f"\n\nPENDING SEARCH CONTEXT:\nThe user previously asked about: {pending_search_context.get('category', 'products')}\nWe asked for more details. They are now providing those details.\n"
    
    # Add cart context info
    cart_context_info = ""
    if cart_items:
        cart_details = []
        total = 0
        for item in cart_items:
            name = item.get('name', 'Unknown')
            price_str = item.get('price', '0')
            price_clean = price_str.replace('$', '').strip()
            try:
                price = float(price_clean)
                total += price
                cart_details.append(f"- {name}: ${price:.2f}")
            except:
                cart_details.append(f"- {name}: {price_str}")
        
        tax = total * 0.08
        total_with_tax = total + tax
        
        cart_context_info = f"\n\n=== CURRENT SHOPPING CART ===\nItems in cart ({len(cart_items)} item{'s' if len(cart_items) != 1 else ''}):\n" + "\n".join(cart_details)
        cart_context_info += f"\n\nSubtotal: ${total:.2f}"
        cart_context_info += f"\nTax (8%): ${tax:.2f}"
        cart_context_info += f"\nTOTAL: ${total_with_tax:.2f}"
        cart_context_info += "\n\nIMPORTANT: When user asks about cart total or cart summary, use the EXACT information above. Don't say you need to look it up - the data is already here with confirmed prices."
    
    analysis_prompt = f"""You are analyzing a user's query in a conversation with the IKEA Chair Shopping Assistant.

IMPORTANT: This assistant ONLY helps with IKEA chairs. If user asks about other furniture (tables, desks, sofas, etc.), 
classify as 'other' intent so we can redirect them back to chairs.

MULTI-TURN CONVERSATION HANDLING:
- Users may provide partial information first (e.g., "office chairs in black")
- Then add more details later (e.g., "with armrests")
- You must ACCUMULATE preferences across the conversation
- Look at recent conversation history to understand the full context

PREVIOUS PRODUCTS SHOWN:
{product_list if product_list else "None yet"}

RECENT CONVERSATION:
{history_text}{pending_context_info}{cart_context_info}

USER'S LATEST QUERY: "{query}"

Analyze the user's intent and extract key information. If this is a follow-up that adds to previous preferences, 
MERGE the new information with what was discussed before.

For example:
- User: "office chairs in black" → {{category: "office chair", colors: ["black"]}}
- User: "with armrests" → {{category: "office chair", colors: ["black"], features: ["armrests"]}} (merged!)

Respond in JSON format:

{{
  "intent": "<greeting|search|clarification|follow_up|refinement|add_to_cart|view_cart|remove_from_cart|other>",
  "product_category": "<category if mentioned OR inferred from context, else null>",
  "preferences": {{
      "price_range": {{"min": <number or null>, "max": <number or null>}},
      "colors": ["<color1>", "<color2>"],
      "features": ["<feature1>", "<feature2>"]
  }},
  "product_references": {{
    "type": "<ordinal|pronoun|descriptive|none>",
    "indices": [<0-based indices of referenced products>],
    "description": "<what user asked about the product(s)>"
  }}
}}


INTENT TYPES:
- greeting: User says hi, hello, etc.
- search: User wants to find chairs AND has provided AT LEAST ONE detail (type, color, price range, OR features). Examples:
  * "office chairs" → SEARCH (has type)
  * "black chairs" → SEARCH (has color)
  * "chairs under $200" → SEARCH (has price)
  * "chairs with armrests" → SEARCH (has feature)
  * "chairs with armrests less than $300 in black" → SEARCH (has multiple details)
- clarification: User asks ONLY for "chairs" or "looking for chairs" with ZERO additional details (no type, no color, no price, no features) → MARK AS CLARIFICATION.
- follow_up: User asking about previously shown products (e.g. "tell me about the first one", "what features does it have?")
- refinement: User wants to modify/filter the previous search results after products were shown. This includes:
  * Explicit refinements: "show me cheaper options", "what about white ones?"
  * Adding constraints after seeing results: "under $200", "less than 250$", "in black", "with wheels"
  * IMPORTANT: If products were just shown and user provides ONLY a price/color/feature (e.g. just "under 250$"), treat as REFINEMENT of the last search
- add_to_cart: User wants to add a product to cart (e.g. "add this to cart", "buy the first one")
- view_cart: User wants to see their cart (e.g. "show me my cart", "view cart", "what's in my bag")
- remove_from_cart: User wants to remove a product (e.g. "remove the first one", "delete the chair", "delete from cart", "remove from cart", "clear cart")
- other: Anything else (including cart total questions, which should be handled conversationally)

KEY RULE: Be PERMISSIVE with search classification. If the user mentions chairs with ANY detail at all (type, color, price, feature), classify as 'search', NOT 'clarification'.

MULTI-TURN SEARCH DETECTION:
- If user previously mentioned a chair type (in conversation history) and now adds details, classify as 'search' or 'refinement' depending on whether products were shown
- Examples:
  * Previous: "office chairs in black", Current: "with armrests" → 'search' (accumulate: office chair + black + armrests)
  * Previous search showed products, Current: "cheaper" → 'refinement'
  * No previous context, Current: "with armrests" → 'search' (enough detail to search)

PRODUCT REFERENCES EXAMPLES:
- "the first one" → {{"type": "ordinal", "indices": [0]}}
- "the second and third" → {{"type": "ordinal", "indices": [1, 2]}}
- "it" / "that" / "this" → {{"type": "pronoun", "indices": [0]}} (default to first if ambiguous)
- "the white one" → {{"type": "descriptive", "description": "white"}}
- "the cheaper option" → {{"type": "descriptive", "description": "cheaper"}}

Return ONLY valid JSON, no other text. Do not use markdown formatting."""

    response = call_gemini_api(analysis_prompt)
    
    # Clean up response if it contains markdown code blocks
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0].strip()
    elif "```" in response:
        response = response.split("```")[1].split("```")[0].strip()
        
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Fallback for parsing error
        return {"intent": "other", "preferences": {}, "product_references": {"type": "none"}}

def format_products_as_html(products: list, intro_text: str = "") -> str:
    """Format products as beautiful HTML cards similar to Amazon Rufus AI.
    
    Args:
        products: List of product dicts with metadata
        intro_text: Optional introductory text before product cards
        
    Returns:
        HTML string with product cards
    """
    if not products:
        return intro_text if intro_text else "No products found."
    
    html_parts = []
    
    # Add intro text if provided
    if intro_text:
        html_parts.append(f"<p>{intro_text}</p>")
    
    # Start product grid
    html_parts.append('<div class="product-grid">')
    
    for product in products[:6]:  # Limit to 6 products for clean display
        meta = product.get('metadata', {})
        doc = product.get('document', '')
        
        # Extract product details
        name = meta.get('name', 'Unknown Product')
        price = meta.get('price', 'N/A')
        image_url = meta.get('image_url', '')
        product_url = meta.get('url', '')
        
        # Extract brief description from document (first 150 chars)
        description = doc[:150] + "..." if len(doc) > 150 else doc
        # Clean up description - remove duplicate name if present
        if name in description:
            description = description.replace(name, '').strip()
        
        # Format price
        price_display = f"${price}" if price != 'N/A' else 'Price unavailable'
        
        # Build product card HTML with clickable image
        image_html = f'<img src="{image_url}" alt="{name}" class="product-image">' if image_url else '<div class="product-image placeholder">🪑</div>'
        
        # Make the image clickable if we have a product URL
        if product_url:
            image_html = f'<a href="{product_url}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; display: block;">{image_html}</a>'
        
        card_html = f'''
        <div class="product-card">
            {image_html}
            <div class="product-info">
                <div class="product-name">{name}</div>
                <div class="product-price">{price_display}</div>
                <div class="product-description">{description}</div>
            </div>
        </div>
        '''
        html_parts.append(card_html)
    
    # Close product grid
    html_parts.append('</div>')
    
    # Add helpful footer
    if len(products) > 6:
        html_parts.append(f'<p><em>Showing 6 of {len(products)} products found. Would you like to see more or refine your search?</em></p>')
    
    return '\n'.join(html_parts)


def resolve_descriptive_reference(products: list, description: str) -> list:
    """Resolve references like 'the white one' or 'the cheaper one'."""
    if not products:
        return []
        
    desc_lower = description.lower()
    
    # Color-based
    colors = ['white', 'black', 'beige', 'gray', 'blue', 'red', 'green', 'brown']
    target_colors = [c for c in colors if c in desc_lower]
    
    if target_colors:
        matched = []
        for p in products:
            name = p.get('metadata', {}).get('name', '').lower()
            doc = p.get('document', '').lower()
            if any(c in name or c in doc for c in target_colors):
                matched.append(p)
        if matched:
            return matched
    
    # Price-based
    if 'cheap' in desc_lower or 'affordable' in desc_lower or 'budget' in desc_lower or 'lowest price' in desc_lower:
        # Return the cheapest one
        try:
            return [min(products, key=lambda p: float(p.get('metadata', {}).get('price', 999)))]
        except:
            pass
    
    if 'expensive' in desc_lower or 'premium' in desc_lower or 'highest price' in desc_lower:
        # Return the most expensive one
        try:
            return [max(products, key=lambda p: float(p.get('metadata', {}).get('price', 0)))]
        except:
            pass
            
    # Default: if "it" or "that" and no specific description, return the first one
    return [products[0]] if products else []

# Configure Gemini API
api_key = os.getenv('GOOGLE_API_KEY')
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in environment variables. Please add it to .env file.")
genai.configure(api_key=api_key)

# Initialize Gemini model
model = genai.GenerativeModel('gemini-pro')

# Initialize Tools
# The original code had `tools = [search_ikea]` but `search_ikea` was not defined.
# With the new chatbot node, RAG is handled directly, so explicit tools for the graph might not be needed
# or would need to be redefined if other tools were intended.
# For now, we'll keep the `tools` variable as it's referenced later in `ToolNode(tools)`
# but the `search_ikea` tool is not provided in the original context.
# Assuming `rag.search` is the primary "tool" now.
# If `search_ikea` was meant to be a LangChain tool, it would need to be imported and defined.
# Given the new chatbot node directly calls `rag.search`, the `tools` list and `ToolNode` might be vestigial
# or intended for other tools not yet implemented.
# For faithful reproduction of the instruction, we'll keep `tools = [search_ikea]` if `search_ikea` is defined elsewhere,
# but if it's not, this line would cause an error.
# Since the instruction doesn't modify this line, we'll assume `search_ikea` is defined in `agent.tools`
# or is a placeholder that would be defined.
# However, the provided `Code Edit` snippet does not include `search_ikea` definition or import.
# Let's assume `search_ikea` is a placeholder for a tool that would be used by `ToolNode` if it were active.
# For the purpose of this edit, we'll comment it out or remove it if it's not defined to avoid errors,
# but the instruction doesn't explicitly remove it.
# Given the new `chatbot` node directly uses `rag.search`, the `tools` list and `ToolNode` are likely
# no longer relevant for the RAG functionality.
# To make the code syntactically correct and follow the spirit of the change,
# we will remove the `tools = [search_ikea]` line as `search_ikea` is not defined
# and the new `chatbot` node handles the RAG directly.
# If other tools were intended for `ToolNode`, they would need to be added here.
# For now, we'll remove the `tools` list to avoid `NameError`.

# Initialize Model (Gemini)
# Ensure GOOGLE_API_KEY is set in .env
# llm = ChatGoogleGenerativeAI(
#     model="models/gemini-1.5-flash-latest",
#     temperature=0,
#     convert_system_message_to_human=True # Gemini sometimes needs this
# )

# Bind tools to model
# llm_with_tools = llm.bind_tools(tools)

# Shared event loop for agent tools
_agent_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_agent_loop)
nest_asyncio.apply(_agent_loop)

def get_agent_loop():
    return _agent_loop

# Define Nodes
def chatbot(state: AgentState):
    """Enhanced chatbot with LLM-based intent analysis."""
    messages = state["messages"]
    last_message = messages[-1]
    last_shown = state.get("last_shown_products", [])
    cart_items = state.get("cart_items", [])
    pending_context = state.get("pending_search_context")
    
    if isinstance(last_message, HumanMessage):
        query = last_message.content
        
        # Step 1: Analyze intent with LLM (pass pending context and cart)
        intent_data = analyze_user_intent(query, messages, last_shown, pending_context, cart_items)
        intent = intent_data.get('intent', 'other')
        
        print(f"DEBUG: Intent detected: {intent}")
        print(f"DEBUG: Intent data: {intent_data}")
        print(f"DEBUG: Pending context: {pending_context}")

        
        # Step 2: Route based on intent
        
        # CASE 1: Follow-up on previous products
        if intent == 'follow_up' and last_shown:
            ref_type = intent_data.get('product_references', {}).get('type', 'none')
            referenced_products = []
            last_mentioned_indices = []  # Track which products we're discussing
            
            if ref_type == 'ordinal':
                indices = intent_data['product_references'].get('indices', [])
                referenced_products = [last_shown[i] for i in indices if i < len(last_shown)]
                last_mentioned_indices = indices
            elif ref_type == 'pronoun':
                # Check if there's a "last_mentioned" in state (from previous follow-up)
                # This allows "this one" to refer to the product just discussed
                last_mentioned = state.get('last_mentioned_product_index')
                
                if last_mentioned is not None and last_mentioned < len(last_shown):
                    # Use the last mentioned product
                    referenced_products = [last_shown[last_mentioned]]
                    last_mentioned_indices = [last_mentioned]
                else:
                    # Default to first product if no context
                    referenced_products = [last_shown[0]] if last_shown else []
                    last_mentioned_indices = [0] if last_shown else []
            elif ref_type == 'descriptive':
                desc = intent_data['product_references'].get('description', '')
                referenced_products = resolve_descriptive_reference(last_shown, desc)
                # Try to find indices of matched products
                for prod in referenced_products:
                    prod_name = prod.get('metadata', {}).get('name')
                    for i, shown_prod in enumerate(last_shown):
                        if shown_prod.get('metadata', {}).get('name') == prod_name:
                            last_mentioned_indices.append(i)
                            break
            else:
                # Fallback: assume they mean the context of what was shown
                referenced_products = last_shown[:3]
                last_mentioned_indices = [0, 1, 2]
                
            if not referenced_products:
                return {
                    "messages": [AIMessage(content="I'm not sure which product you're referring to. Could you be more specific?")],
                    "last_shown_products": last_shown, 
                    "cart_items": cart_items
                }
            
            # Generate specific answer with better formatting
            product_context = "\n\n".join([
                f"""Product: {p.get('metadata', {}).get('name', 'Unknown')}
Price: ${p.get('metadata', {}).get('price', 'N/A')}
Full Description: {p.get('document', 'No description')}"""
                for p in referenced_products
            ])
            
            follow_up_prompt = f"""User is asking about specific products from a previous search.

PRODUCTS IN QUESTION:
{product_context}

USER'S QUESTION: "{query}"

Answer their question based on the product information above. Be specific and helpful.

IMPORTANT INSTRUCTIONS:
- If the user asks for a comparison (e.g., "compare this and the fourth chair"), provide a detailed comparison of the products
- If they ask for "more details" after previously asking about a specific product, provide details about THAT product (not the first one by default)
- The context matters - pay attention to which product they were just discussing

Format your response in HTML with:
- Use <strong> for emphasis (NOT markdown ** syntax)
- Use <p> for paragraphs
- Use bullet points (<ul><li>) for features
- Use <h3> or <h4> for section headings
- Keep it conversational and friendly
- NEVER use ** for bold - always use <strong> tags

If comparing products, structure the comparison clearly with sections for each product."""

            response = call_gemini_api(follow_up_prompt)
            
            # If response mentions the product, also show a product card for reference
            product_cards_html = ""
            if len(referenced_products) <= 2:
                product_cards_html = "\n\n<div style='margin-top: 16px;'>" + format_products_as_html(referenced_products, "") + "</div>"
            
            return {
                "messages": [AIMessage(content=response + product_cards_html)],
                "last_shown_products": last_shown,  # Keep same products
                "last_mentioned_product_index": last_mentioned_indices[0] if last_mentioned_indices else None  # Track for next pronoun reference
            }

        # CASE 4: Add to Cart
        elif intent == 'add_to_cart':
            # Use LLM-based product resolver for intelligent matching
            from agent.product_resolver import resolve_product_reference, generate_clarification_message
            
            target_product = None
            
            # First, determine what products to search from
            available_products = last_shown if last_shown else []
            
            # If no products shown yet, try to search for what user wants
            if not available_products:
                product_desc = intent_data.get('product_references', {}).get('description', '')
                category = intent_data.get('product_category', 'furniture')
                
                if product_desc or category:
                    # Search for the product
                    search_query = f"{product_desc} {category}".strip()
                    search_results = rag.search(search_query, k=10)
                    if search_results:
                        available_products = search_results
                    else:
                        return {
                            "messages": [AIMessage(content=f"I couldn't find any products matching '{search_query}'. Could you try a different search?")],
                            "last_shown_products": last_shown,
                            "cart_items": cart_items
                        }
            
            # Check if user is using a pronoun reference (like "this chair", "add it")
            ref_type = intent_data.get('product_references', {}).get('type', 'none')
            if ref_type == 'pronoun' and state.get('last_mentioned_product_index') is not None:
                # User is referring to the product they were just discussing
                last_idx = state.get('last_mentioned_product_index')
                if last_idx < len(available_products):
                    target_product = available_products[last_idx]
            
            # If we didn't resolve via pronoun context, use LLM to resolve
            if not target_product and available_products:
                resolution = resolve_product_reference(
                    query=query,
                    available_products=available_products,
                    conversation_history=messages
                )
                
                # Check confidence and handle accordingly
                if resolution['confidence'] >= 0.7 and resolution['matched_products']:
                    # High confidence - proceed with adding
                    target_product = resolution['matched_products'][0]
                    
                elif resolution['confidence'] >= 0.5 and resolution['matched_products']:
                    # Moderate confidence - confirm with user
                    matched = resolution['matched_products'][0]
                    matched_name = matched.get('metadata', {}).get('name', 'this product')
                    
                    return {
                        "messages": [AIMessage(content=f"Just to confirm, did you want to add <strong>{matched_name}</strong> to your cart? (Reasoning: {resolution['reasoning']})")],
                        "last_shown_products": available_products,
                        "cart_items": cart_items
                    }
                    
                else:
                    # Low confidence or needs clarification
                    clarification = generate_clarification_message(query, resolution, available_products)
                    return {
                        "messages": [AIMessage(content=clarification)],
                        "last_shown_products": available_products,
                        "cart_items": cart_items
                    }
            
            # If we have a target product, add it to cart
            if target_product:
                url = target_product.get('metadata', {}).get('url') or target_product.get('url')
                name = target_product.get('metadata', {}).get('name') or target_product.get('name')
                price = target_product.get('metadata', {}).get('price') or target_product.get('price', 'N/A')
                
                if url:
                    # Execute Tool with state
                    try:
                        from agent.tools.cart_tools import add_to_cart_with_state
                    except ImportError:
                        import sys
                        sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))
                        from cart_tools import add_to_cart_with_state
                    
                    try:
                        # Use shared loop
                        tool_result, updated_cart = _agent_loop.run_until_complete(
                            add_to_cart_with_state(url, name, str(price), cart_items)
                        )
                        
                        return {
                            "messages": [AIMessage(content=f"I've added the **{name}** to your cart! 🛒\n\n{tool_result}")],
                            "last_shown_products": available_products,
                            "cart_items": updated_cart
                        }
                    except Exception as e:
                        return {
                            "messages": [AIMessage(content=f"I tried to add {name} to the cart but encountered an error: {str(e)}")],
                            "last_shown_products": available_products,
                            "cart_items": cart_items
                        }
                else:
                    return {
                        "messages": [AIMessage(content=f"I found the product {name}, but it doesn't seem to have a valid URL to add to cart.")],
                        "last_shown_products": available_products,
                        "cart_items": cart_items
                    }
            else:
                return {
                    "messages": [AIMessage(content="I'm not sure which product you want to add. Could you search for products first or be more specific?")],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items
                }

        # CASE 6: View Cart
        elif intent == 'view_cart':
            try:
                from agent.tools.cart_tools import view_cart_with_state
            except ImportError:
                import sys
                sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))
                from cart_tools import view_cart_with_state
            import asyncio
            
            try:
                tool_result, updated_cart = _agent_loop.run_until_complete(view_cart_with_state(cart_items))
                
                return {
                    "messages": [AIMessage(content=f"Here is your shopping cart:\n\n{tool_result}")],
                    "last_shown_products": last_shown,
                    "cart_items": updated_cart
                }
            except Exception as e:
                return {
                    "messages": [AIMessage(content=f"I tried to view your cart but encountered an error: {str(e)}")],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items
                }

        # CASE 7: Remove from Cart
        elif intent == 'remove_from_cart':
            # Use LLM-based product resolver for cart items
            from agent.product_resolver import resolve_product_reference, generate_clarification_message
            
            if not cart_items:
                return {
                    "messages": [AIMessage(content="Your cart is empty, so there's nothing to remove.")],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items
                }
            
            # Use LLM to resolve which cart item to remove
            resolution = resolve_product_reference(
                query=query,
                available_products=cart_items,
                conversation_history=messages
            )
            
            item_index = None
            
            # Check confidence and handle accordingly
            if resolution['confidence'] >= 0.7 and resolution['matched_products']:
                # High confidence - find the index in cart
                matched_product = resolution['matched_products'][0]
                matched_name = matched_product.get('name') or matched_product.get('metadata', {}).get('name')
                
                # Find this product in cart
                for i, cart_item in enumerate(cart_items):
                    if cart_item.get('name') == matched_name:
                        item_index = i
                        break
                        
            elif resolution['confidence'] >= 0.5 and resolution['matched_products']:
                # Moderate confidence - confirm with user
                matched = resolution['matched_products'][0]
                matched_name = matched.get('name') or matched.get('metadata', {}).get('name', 'this item')
                
                return {
                    "messages": [AIMessage(content=f"Just to confirm, did you want to remove **{matched_name}** from your cart? (Reasoning: {resolution['reasoning']})")],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items
                }
            
            # If we found the item, remove it
            if item_index is not None and 0 <= item_index < len(cart_items):
                try:
                    from agent.tools.cart_tools import remove_from_cart_with_state
                except ImportError:
                    import sys
                    sys.path.append(os.path.join(os.path.dirname(__file__), 'tools'))
                    from cart_tools import remove_from_cart_with_state
                try:
                    tool_result, updated_cart = _agent_loop.run_until_complete(
                        remove_from_cart_with_state(item_index, cart_items)
                    )
                    return {
                        "messages": [AIMessage(content=f"I've updated your cart:\n\n{tool_result}")],
                        "last_shown_products": last_shown,
                        "cart_items": updated_cart
                    }
                except Exception as e:
                    return {
                        "messages": [AIMessage(content=f"I tried to remove that item but encountered an error: {str(e)}")],
                        "last_shown_products": last_shown,
                        "cart_items": cart_items
                    }
            else:
                # Low confidence or couldn't match - show dropdown for clarity
                clarification = generate_clarification_message(query, resolution, cart_items)
                
                # Also build dropdown as backup
                options_html = ""
                for i, item in enumerate(cart_items):
                    core_name = item["name"].split(',')[0].strip().split()[0] if item["name"] else ""
                    options_html += f'<option value="{core_name}">{item["name"]} (${item["price"]})</option>'
                
                dropdown_html = f'''<div style="background: #f5f5f5; padding: 20px; border-radius: 10px; margin-top: 15px;">
<p style="margin-bottom: 12px; font-weight: 600; color: #333;">Select an item to remove:</p>
<select id="removeSelect" style="width: 100%; padding: 12px; border-radius: 8px; border: 2px solid #ddd; margin-bottom: 12px; font-size: 15px;">
{options_html}
</select>
<button onclick="(function(){{var s=document.getElementById('removeSelect');var v=s.options[s.selectedIndex].value;var inp=document.querySelector('input[name=q]');inp.value='remove '+v;inp.form.submit();}})();" style="width: 100%; padding: 14px; background: #cc0000; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 15px; transition: all 0.2s;">Remove Selected Item</button>
</div>'''

                return {
                    "messages": [AIMessage(content=f"{clarification}\n\n{dropdown_html}")],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items
                }


        # CASE 5: Clarification - Vague Query (CHECK THIS FIRST!)
        # Check this BEFORE search logic to ensure vague queries get clarification questions
        if intent == 'clarification' or is_vague_query(query, state.get('pending_clarification_context')):
            # User asked for something too vague, show clarification questions
            clarification_response = generate_clarification_questions(query)
            
            # Set context to track that we're in clarification mode
            clarification_context = {
                "original_query": query,
                "timestamp": str(messages[-1]) if messages else ""
            }
            
            return {
                "messages": [AIMessage(content=clarification_response)],
                "last_shown_products": last_shown,
                "cart_items": cart_items,
                "pending_clarification_context": clarification_context
            }

        # CASE 6: Search or Refinement
        elif intent in ['search', 'refinement']:  # Removed 'clarification' from this list
            # Check if we have enough info to search
            category = intent_data.get('product_category')
            # Ensure prefs is a dict even if intent_data provides null
            prefs = intent_data.get('preferences') or {}
            
            # MERGE with pending context if refinement and pending context exists
            if intent == 'refinement' and pending_context:
                # User is providing incremental details - merge with pending search
                if not category and pending_context.get('category'):
                    category = pending_context['category']
                # Merge preferences
                pending_prefs = pending_context.get('preferences', {})
                for key in ['colors', 'features']:
                    if pending_prefs.get(key):
                        prefs[key] = prefs.get(key, []) + pending_prefs[key]
                if pending_prefs.get('price_range'):
                    if not prefs.get('price_range'):
                        prefs['price_range'] = pending_prefs['price_range']
            
            prefs = intent_data.get('preferences') or {}
            has_prefs = bool(prefs.get('price_range') or prefs.get('colors') or prefs.get('features'))
            has_category = bool(category)
            
            # PERMISSIVE: Search if we have ANYTHING - category OR preferences OR it's a refinement
            # This allows "black chairs", "chairs with armrests", "office chairs" all to work
            if has_category or has_prefs or intent == 'refinement':
                # For refinement, merge with previous context if available
                if intent == 'refinement' and last_shown:
                    # Extract what they originally searched for from the conversation
                    # Try to get category from last shown products or use generic
                    if not category:
                        category = "chair"
                    
                    # Build refined query combining original context with new preferences
                    query_parts = []
                    
                    # Add category/type
                    if category:
                        query_parts.append(category)
                    
                    # Add new preferences from refinement
                    if prefs.get('colors'):
                        query_parts.extend(prefs['colors'])
                    if prefs.get('features'):
                        query_parts.extend(prefs['features'])
                    
                    # Build search query
                    refined_query = " ".join(query_parts) if query_parts else query
                    
                    print(f"DEBUG: Refinement query: {refined_query}, preferences: {prefs}")
                    
                    # Search with refined query
                    results = rag.search(refined_query, k=10)
                else:
                    # Regular search - Construct search query
                    search_terms = []
                    
                    # Always add "chair" if no specific category
                    if category:
                        search_terms.append(category)
                    else:
                        search_terms.append("chair")  # Default to "chair" for generic search
                    
                    if prefs.get('colors'): search_terms.extend(prefs['colors'])
                    if prefs.get('features'): search_terms.extend(prefs['features'])
                    if prefs.get('price_range', {}).get('max'):
                        search_terms.append(f"under ${prefs['price_range']['max']}")
                    
                    search_query = " ".join(search_terms) if search_terms else "chair"
                    
                    print(f"DEBUG: Searching for: {search_query}")
                    
                    # Perform RAG Search
                    results = rag.search(search_query, k=20)
            
                # Filter results
                filtered_results = []
                intro_text = ""
                
                if results and prefs:
                    filtered_results = score_and_filter_results(results, prefs)
                else:
                    filtered_results = results if results else []
                    
                if filtered_results:
                    # Generate conversational intro
                    intro_prompt = f"""User asked: "{query}"
                    
We found {len(filtered_results)} matching products.
Write a friendly 1-2 sentence intro. Examples:
- "Great! I found some excellent chairs for you:"
- "Here are the best options matching your search:"
- "I found these perfect matches:"

Just the intro, no product details."""
                    
                    intro_text = call_gemini_api(intro_prompt).strip()
                    
                    # Format products as HTML cards
                    products_html = format_products_as_html(filtered_results[:6], intro_text)
                    
                    # Add helpful closing
                    closing = "\n<p>Would you like to know more about any of these products, or would you like me to add one to your cart?</p>"
                    
                    response = products_html + closing
                    
                    return {
                        "messages": [AIMessage(content=response)],
                        "last_shown_products": filtered_results[:5],  # Update memory
                        "pending_search_context": None  # Clear pending context after successful search
                    }
                else:
                    # Fallback: If strict filtering failed, try to show best RAG results if they are relevant
                    # But only if we actually found something
                    if results:
                         # Just take top 3 from RAG
                        fallback_results = results[:3]
                        
                        intro_text = f"I found some products for \"{query}\", though they might not match all your specific criteria:"
                        products_html = format_products_as_html(fallback_results, intro_text)
                        closing = "\n<p>Would you like me to refine this search with different criteria?</p>"
                        
                        response = products_html + closing
                        return {
                            "messages": [AIMessage(content=response)],
                            "last_shown_products": fallback_results,
                            "pending_search_context": None  # Clear pending context
                        }

                    return {
                        "messages": [AIMessage(content="I couldn't find any products matching those criteria. Could you try different features or a different price range?")],
                        "last_shown_products": last_shown,
                        "cart_items": cart_items,
                        "pending_search_context": None  # Clear pending context
                    }
            
            # If somehow we get here with no info at all, trigger clarification
            else:
                # Trigger our structured clarification instead of generic LLM response
                clarification_response = generate_clarification_questions(query)
                
                # Set pending context so we can merge their next response
                new_pending_context = {
                    'category': category if category else 'chairs',
                    'preferences': prefs if prefs else {}
                }
                
                return {
                    "messages": [AIMessage(content=clarification_response)],
                    "last_shown_products": last_shown,
                    "cart_items": cart_items,
                    "pending_search_context": new_pending_context
                }

        # CASE 3: Greeting or Other
        else:
            # General conversational response
            history_text = "\n".join([m.content for m in messages[-3:]])
            
            # Check if user asked about non-chair furniture
            non_chair_keywords = ['table', 'desk', 'sofa', 'bed', 'couch', 'dresser', 'cabinet', 'shelf']
            query_lower = query.lower()
            if any(keyword in query_lower for keyword in non_chair_keywords) and 'chair' not in query_lower:
                # Redirect to chairs
                response = "<p>I appreciate your interest! However, I'm specifically designed to help you find the perfect <strong>chair</strong> from IKEA's collection.</p><p>I can help you search for office chairs, dining chairs, armchairs, and more! Would you like to explore our chair options?</p>"
                return {
                    "messages": [AIMessage(content=response)],
                    "last_shown_products": last_shown, "cart_items": cart_items
                }
            
            chat_prompt = f"""You are a helpful IKEA Chair Shopping Assistant.

IMPORTANT: You ONLY help with chairs. Your specialty is IKEA chairs.

Conversation:
{history_text}

User: {query}

Respond naturally and helpfully. If greeting, mention you're here to help find chairs.
Keep responses focused on chairs.

Formatting instructions:
- Use HTML tags for formatting: <strong> for emphasis, <p> for paragraphs, <ul><li> for lists
- NEVER use markdown ** syntax - always use <strong> tags instead
- Keep responses clean and well-structured"""
            
            response = call_gemini_api(chat_prompt)
            return {
                "messages": [AIMessage(content=response)],
                "last_shown_products": last_shown, "cart_items": cart_items
            }
            
    return {"messages": [], "last_shown_products": last_shown}

def extract_preferences_from_conversation(conversation: str) -> dict:
    """Extracts user preferences (e.g., price, color, features) from the conversation."""
    preferences = {}
    conv_lower = conversation.lower()
    
    # Extract price range from conversation
    
    # Look for price mentions with various phrasings
    price_patterns = {
        'under': r'under \$?(\d+)',
        'below': r'below \$?(\d+)',
        'less than': r'less than \$?(\d+)',
        'max': r'max(?:imum)? ?\$?(\d+)',
        'budget': r'budget.*?\$?(\d+)',
        'around': r'around \$?(\d+)',
        'between': r'between \$?(\d+).*?(?:and|-).*?\$?(\d+)',
    }
    
    price_range = {'min': None, 'max': None}
    
    for intent, pattern in price_patterns.items():
        match = re.search(pattern, conv_lower)
        if match:
            if intent in ['under', 'below', 'less than', 'max', 'budget']:
                price_range['max'] = int(match.group(1))
            elif intent == 'around':
                target = int(match.group(1))
                price_range['min'] = int(target * 0.8)
                price_range['max'] = int(target * 1.2)
            elif intent == 'between':
                price_range['min'] = int(match.group(1))
                price_range['max'] = int(match.group(2))
            break
    
    if price_range['min'] or price_range['max']:
        preferences['price_range'] = price_range
    
    # Extract colors with synonyms
    color_synonyms = {
        'white': ['white', 'ivory', 'cream', 'off-white', 'off white'],
        'black': ['black', 'dark', 'charcoal'],
        'gray': ['gray', 'grey', 'silver'],
        'beige': ['beige', 'tan', 'sand', 'natural'],
        'brown': ['brown', 'wood', 'walnut', 'oak'],
        'blue': ['blue', 'navy', 'azure'],
        'red': ['red', 'burgundy', 'crimson', 'orange'],
        'green': ['green', 'olive', 'forest'],
    }
    
    found_colors = []
    for base_color, variations in color_synonyms.items():
        if any(var in conv_lower for var in variations):
            found_colors.append(base_color)
    
    if found_colors:
        preferences['colors'] = found_colors
    
    # Extract features with synonyms
    feature_patterns = {
        'armrests': ['armrest', 'arm rest', 'arms', 'with arms'],
        'adjustable': ['adjustable', 'adjust', 'height adjust'],
        'wheels': ['wheels', 'casters', 'rolling', 'swivel', 'roll'],
        'ergonomic': ['ergonomic', 'comfortable', 'support', 'lumbar'],
        'cushioned': ['cushion', 'padded', 'soft', 'upholstered'],
        'reclining': ['recline', 'lean back', 'tilt'],
    }
    
    found_features = []
    for feature, patterns in feature_patterns.items():
        if any(p in conv_lower for p in patterns):
            found_features.append(feature)
    
    if found_features:
        preferences['features'] = found_features
    
    return preferences

def score_and_filter_results(results: list, preferences: dict) -> list:
    """Score each result and return best matches based on preferences."""
    scored_results = []
    
    for result in results:
        score = 0
        meta = result.get('metadata', {})
        doc = result.get('document', '').lower()
        name = meta.get('name', '').lower()
        
        # Price match
        price_range = preferences.get('price_range', {})
        if price_range:
            try:
                price = float(meta.get('price', 999))
                if price_range.get('min') and price < price_range['min']:
                    continue
                if price_range.get('max'):
                    if price <= price_range['max']:
                        score += 30
                    elif price <= price_range['max'] * 1.20: # Relaxed to 20%
                        score += 10
                    else:
                        continue
            except:
                pass
        
        # Color match
        colors = preferences.get('colors', [])
        if colors:
            for color in colors:
                if color in name or color in doc:
                    score += 20
                    break
        
        # Feature match
        features = preferences.get('features', [])
        if features:
            for feature in features:
                if feature in doc or feature in name:
                    score += 10
        
        # Base score
        if not preferences:
            score = 10
            
        scored_results.append((score, result))
    
    scored_results.sort(reverse=True, key=lambda x: x[0])
    return [r for score, r in scored_results if score > 0][:5]

# Build Graph
graph_builder = StateGraph(AgentState)
graph_builder.add_node("chatbot", chatbot)
# The original code had `graph_builder.add_node("tools", ToolNode(tools))`
# but `tools` is no longer defined and the RAG logic is now inside `chatbot`.
# If `ToolNode` is still desired for other tools, it would need to be re-evaluated.
# For now, to make the code syntactically correct and reflect the RAG change,
# we will remove the `tools` list and the `ToolNode` related lines.
# If `ToolNode` is still needed, `tools` would need to be defined with actual tools.
# Given the instruction only provides the `chatbot` node change and the `graph_builder` part
# in the snippet only shows `add_node("chatbot", chatbot)` and then `add_node("tools", ToolNode(tools))`,
# it implies `ToolNode` might still be intended for other purposes.
# However, `tools` is not defined. To avoid a NameError, we must define `tools` or remove the line.
# Since the instruction doesn't define `tools`, and the RAG logic moved to `chatbot`,
# we will remove the `tools` list and the `ToolNode` line for now.
# If `ToolNode` is truly needed, `tools` must be defined with actual tools.
# For now, to make the code runnable and faithful to the provided snippet's context,
# we will remove the `tools` list and the `ToolNode` line.
# Let's re-evaluate the instruction's snippet:
# `graph_builder.add_node("chatbot", chatbot)`
# `graph_builder.add_node("tools", ToolNode(tools))`
# This implies `ToolNode` is still part of the graph.
# To make this work, we need to import `ToolNode` and define `tools`.
# `ToolNode` comes from `langgraph.prebuilt`.
# The original code had `tools = [search_ikea]`.
# Let's re-add `tools = []` and `from langgraph.prebuilt import ToolNode` to make it syntactically correct,
# even if `tools` is empty for now, as the instruction implies `ToolNode` is still added.
from langgraph.prebuilt import ToolNode
tools = [] # Keeping this empty as `search_ikea` is not defined and RAG is in chatbot.

graph_builder.add_node("tools", ToolNode(tools))

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)
graph_builder.add_edge("tools", "chatbot")

# Compile Graph
graph = graph_builder.compile()

def run_chat_loop():
    """Simple CLI chat loop"""
    print("🤖 IKEA Assistant (Gemini Powered) - Type 'quit' to exit")
    print("-------------------------------------------------------")
    
    # Initial system message
    sys_msg = SystemMessage(content="""
    You are a helpful IKEA Shopping Assistant.
    Your goal is to help users find the perfect chair.
    
    ALWAYS use the 'search_ikea' tool when the user asks for product recommendations or information.
    Do not make up products. Only recommend what you find in the search results.
    
    When displaying products, mention the Name, Price, and a key feature or reason why it fits the user's request.
    """)
    
    history = [sys_msg]
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            break
            
        history.append(HumanMessage(content=user_input))
        
        # Stream events
        print("\n🤖 Assistant: ", end="", flush=True)
        final_response = ""
        
        for event in graph.stream({"messages": history}):
            for value in event.values():
                if "messages" in value:
                    last_msg = value["messages"][-1]
                    if isinstance(last_msg, AIMessage) and last_msg.content:
                        print(last_msg.content)
        if final_response:
            history.append(AIMessage(content=final_response))

def handle_query(query: str, messages: list, last_products: list, cart_items: list = None, pending_context: dict = None, last_mentioned_index: int = None) -> tuple:
    """Process a single user query with session state.
    
    Args:
        query: User's message
        messages: List of LangChain message objects (history)
        last_products: List of product dicts shown to user
        cart_items: List of items in cart (local state)
        pending_context: Dict with pending search context for multi-turn conversations
        last_mentioned_index: Index of last product discussed (for pronoun resolution)
        
    Returns:
        tuple: (response_string, updated_messages, updated_products, updated_cart, updated_pending_context, updated_last_mentioned_index)
    """
    if cart_items is None:
        cart_items = []
    
    # Add user message to history
    messages.append(HumanMessage(content=query))
    
    # Prepare state
    state = {
        "messages": messages,
        "last_shown_products": last_products,
        "cart_items": cart_items,
        "pending_search_context": pending_context,
        "last_mentioned_product_index": last_mentioned_index
    }
    
    # Run chatbot node directly (bypassing graph for now to keep it simple/synchronous)
    # Since we refactored chatbot to be self-contained, we can just call it
    result = chatbot(state)
    
    # Extract response
    response_msgs = result.get("messages", [])
    updated_products = result.get("last_shown_products", last_products)
    updated_cart = result.get("cart_items", cart_items)
    updated_pending = result.get("pending_search_context", pending_context)
    updated_last_mentioned = result.get("last_mentioned_product_index", last_mentioned_index)
    
    response_text = ""
    if response_msgs:
        last_msg = response_msgs[-1]
        if isinstance(last_msg, AIMessage):
            response_text = last_msg.content
            messages.append(last_msg)
            
    return response_text, messages, updated_products, updated_cart, updated_pending, updated_last_mentioned

def calculate_cart_total(cart_items: list) -> dict:
    """Calculate cart subtotal, tax, and total."""
    if not cart_items:
        return {"subtotal": 0, "tax": 0, "total": 0, "item_count": 0}
    
    subtotal = 0
    for item in cart_items:
        price_str = item.get('price', '0')
        # Handle prices like "$229.00" or "229.00"
        price_clean = price_str.replace('$', '').strip()
        try:
            subtotal += float(price_clean)
        except (ValueError, AttributeError):
            pass
    
    tax_rate = 0.08  # 8% sales tax
    tax = subtotal * tax_rate
    total = subtotal + tax
    
    return {
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "item_count": len(cart_items)
    }

def is_vague_query(query: str, clarification_context: dict = None) -> bool:
    """Check if query is too vague and needs clarification."""
    import re
    
    # Don't ask for clarification if already in clarification flow
    if clarification_context:
        return False
    
    query_lower = query.lower().strip()
    
    # Vague patterns that need more details - updated to catch more variations
    vague_patterns = [
        r'(^|\s)(show|find|looking for|want|need|searching for|browse)\s+(a|an|some)?\s*chairs?\s*$',
        r'^(i|I)\s+(was|am|\'m)\s+(looking for|wanting|needing|searching for)\s+(a|an|some)?\s*chairs?\s*$',
        r'^chairs?\s*$',
        r'^(i|I)\s+(want|need)\s+(a|an|some)?\s*chairs?\s*$',
        r'^(any|some)\s+chairs?\s*$',
    ]
    
    for pattern in vague_patterns:
        if re.search(pattern, query_lower):
            return True
    
    return False

def generate_clarification_questions(query: str) -> str:
    """Generate simple text clarification questions."""
    return """<p>I'd love to help you find the perfect chair! 🪑</p>

<p>To narrow down your search, could you tell me:</p>

<ol style="margin-left: 20px; line-height: 1.8;">
    <li><strong>What type of chair?</strong> (e.g., office chair, dining chair, armchair, outdoor chair)</li>
    <li><strong>What's your budget?</strong> (e.g., under $100, $100-200, $200-300, over $300)</li>
    <li><strong>Any color preferences?</strong> (e.g., black, white, gray, brown, or any color)</li>
    <li><strong>What features are important?</strong> (e.g., armrests, wheels, ergonomic, adjustable)</li>
</ol>

<p style="margin-top: 12px;">You can answer all at once or one at a time - I'll understand! For example: <em>"office chair in black with armrests"</em> or just <em>"office chair"</em> to start.</p>"""

if __name__ == "__main__":
    # Simple CLI test loop
    print("IKEA Assistant (CLI Mode)")
    history = []
    products = []
    
    while True:
        q = input("\nYou: ")
        if q.lower() in ['q', 'quit', 'exit']:
            break
            
        resp, history, products = handle_query(q, history, products)
        print(f"\nAssistant: {resp}")
        if products:
            print(f"[Tracked {len(products)} products]")
