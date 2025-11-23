# IKEA Shopping Assistant 🛋️🤖

A conversational AI shopping assistant for IKEA that combines natural language understanding, semantic search, and browser automation to create an intelligent, clickless cart management experience.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![Playwright](https://img.shields.io/badge/Playwright-1.47-orange)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple)

---

## ✨ Features

### 🎯 Smart Clarification Flow (NEW!)
- **Vague Query Detection**: Automatically detects queries like "looking for chairs" without details
- **Interactive Chips**: Clickable options for chair type, price range, and colors
- **Multi-Turn Conversations**: Understands refinements like "less than $250" after showing results
- **Context Awareness**: Remembers previous searches and merges new constraints

### 🛒 Intelligent Cart Operations
- **Natural Language**: Say "add the ergonomic chair with armrests" instead of "add the first one"
- **LLM-Powered Matching**: Semantic understanding of product descriptions
- **Automated Actions**: Browser automation adds/removes items automatically
- **Video Recordings**: Every cart action recorded with split-screen display
- **Cart Total Calculation**: Ask "what's my cart total?" for detailed breakdown

### 🎥 Split-Screen UI (NEW!)
- **Dynamic Layout**: Chat (60%) + Video Panel (40%) during cart operations
- **Closeable Panel**: × button returns to full-width chat
- **Smooth Transitions**: 0.3s animations for professional feel
- **Auto-Detection**: Videos automatically extracted to side panel

### 🔍 RAG-Powered Search
- **Semantic Search**: Find products using natural language
- **Hybrid Matching**: Combines keyword and vector search
- **Smart Filtering**: Price range, colors, features extraction
- **ChromaDB**: Fast vector similarity search

### 💬 Conversational Interface
- **Context Awareness**: Remembers previous searches and cart items
- **Product Cards**: Beautiful HTML product displays with images
- **Formatted Responses**: HTML formatting with emphasis and bullet points
- **Session Management**: Persistent state across interactions

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Google API Key (for Gemini LLM)
- Chromium/Chrome (for Playwright)

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd ClickelssUI
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers**
```bash
playwright install chromium
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

5. **Run the application**
```bash
python web/app.py
```

6. **Open your browser**
```
http://127.0.0.1:5000
```

---

## 💡 Usage Examples

### Clarification Flow
```
You: "looking for chairs"
Agent: [Shows interactive chips for type, price, color]
You: [Clicks "Office chair" and "Under $200"]
Agent: [Displays filtered results]
```

### Multi-Turn Refinement
```
You: "office chairs with armrests"
Agent: [Shows 5 results]
You: "less than $250"
Agent: [Refines results to show only chairs under $250]
```

### Cart Total
```
You: "what's my cart total?"
Agent: Your cart has:
       • FLINTAN Office chair - $139.00
       
       Subtotal: $139.00
       Tax (8%): $11.12
       TOTAL: $150.12
```

### Smart Product Selection
```
You: "add the chair with lumbar support"
Agent: ✅ Added MARKUS Office chair to cart!
       [Split-screen shows video of action]
```

---

## 📁 Project Structure

```
ClickelssUI/
├── agent/                     # AI Agent Layer
│   ├── ikea_agent.py         # Main conversational agent
│   ├── product_resolver.py   # LLM product matching
│   ├── rag_tool.py           # RAG search interface
│   └── tools/cart_tools.py   # Cart operation tools
│
├── automation/                # Browser Automation
│   ├── browser_manager.py    # Playwright session management
│   └── ikea_cart.py          # Cart automation + video recording
│
├── scraper/                   # Data Collection
│   ├── ikea_scraper.py       # Web scraper
│   ├── rag_manager.py        # ChromaDB manager
│   └── data_processor.py     # Data cleaning
│
├── web/                       # Web Interface
│   └── app.py                # Flask application
│
├── data/                      # Product Data
│   ├── raw/                  # Scraped JSON
│   └── chroma_db/            # Vector embeddings
│
└── tests/                     # Test Suite
    ├── test_product_selection_simple.py
    └── test_remove_from_cart.py
```

---

## 🛠️ Technology Stack

### Core Technologies
- **Python 3.11** - Main language
- **Flask 3.1** - Web framework
- **Playwright 1.47** - Browser automation

### AI/LLM
- **Google Gemini 2.5 Flash** - Primary LLM
- **LangGraph 0.2** - Agent orchestration
- **LangChain Core** - Tool integration

### Data & Search
- **ChromaDB 0.5** - Vector database
- **ONNX Embeddings** - Default embedding model
- **Semantic Search** - Hybrid keyword + vector

---

## 🔧 Configuration

### Environment Variables (.env)
```bash
# Required
GOOGLE_API_KEY=your_gemini_api_key_here

# Optional (for OpenAI embeddings)
OPENAI_API_KEY=your_openai_key_here
```

### Application Settings
- **Port**: 5000 (default)
- **Debug Mode**: Enabled in development
- **Session Storage**: File-based (`flask_session/`)
- **Video Storage**: `videos/` (auto-created, cleared on restart)
- **Screenshot Storage**: `screenshots/` (auto-created)

---

## 📊 Key Metrics

| Metric | Performance |
|--------|------------|
| Product Search | < 1 second |
| LLM Processing | ~1-2 seconds |
| Cart Operations | ~5-8 seconds |
| Video Recording | Real-time |
| Multi-Turn Refinement | < 1 second |

---

## � Recent Updates

### Version 3.0 - Enhanced Conversations (November 2025)
- ✅ Clarification flow for vague queries with interactive chips
- ✅ Multi-turn conversation with refinement support
- ✅ Cart total calculation via LLM with detailed breakdown
- ✅ Split-screen UI with closeable video panel
- ✅ Improved follow-up formatting with HTML and product cards

### Version 2.0 - LLM Product Selection
- ✅ Natural language product matching
- ✅ Confidence-based decision making
- ✅ Automatic clarification for ambiguous queries
- ✅ Comprehensive test suite (5/5 passing)

### Version 1.0 - Initial Release
- ✅ RAG-powered product search
- ✅ Browser automation with Playwright
- ✅ Video recording of cart actions
- ✅ Flask web interface

---

## 🚧 Known Limitations

1. **Single Session**: Only one user session supported at a time
2. **IKEA Website Changes**: May break if IKEA updates their UI
3. **Browser State**: Requires manual login to IKEA first (cookies persist)
4. **Video Storage**: Videos cleared on server restart

---

## 🔮 Future Enhancements

- [ ] Multi-category support (beyond chairs)
- [ ] User preference learning
- [ ] Price tracking and alerts
- [ ] Image-based product search
- [ ] Multi-language support
- [ ] Voice interface
- [ ] Mobile app

---

## 📚 Documentation

- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Detailed system architecture
- **[.env.example](./.env.example)** - Environment configuration template

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## 📝 License

This project is for educational purposes. Please respect IKEA's terms of service and robots.txt.

---

## 🙏 Acknowledgments

- **LangChain** - Agent framework
- **LangGraph** - State machine orchestration
- **Playwright** - Browser automation
- **ChromaDB** - Vector database
- **Google Gemini** - LLM capabilities

---

## 📧 Support

For issues or questions:
1. Check existing issues
2. Review documentation
3. Create a new issue with details

---

**Built with ❤️ using LLMs, RAG, and Browser Automation**

**Version**: 3.0.0  
**Last Updated**: November 2025  
**Status**: ✅ Production Ready
