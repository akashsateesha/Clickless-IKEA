import os
import sys
# Add parent directory to path so we can import agent module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, render_template_string, session, send_from_directory
import markdown
from flask_session import Session
from agent.ikea_agent import handle_query
import shutil
import time

app = Flask(__name__)

# FRESH START: Delete old data on startup
session_dir = os.path.join(os.path.dirname(__file__), 'flask_session')
if os.path.exists(session_dir):
    try:
        shutil.rmtree(session_dir)
        print("✅ Cleared old session data")
    except Exception as e:
        print(f"⚠️ Could not delete session data: {e}")

# Clear videos directory
videos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
if os.path.exists(videos_dir):
    try:
        shutil.rmtree(videos_dir)
        os.makedirs(videos_dir)
        print("✅ Cleared old videos")
    except Exception as e:
        print(f"⚠️ Could not clear videos: {e}")

# Clear screenshots directory
screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screenshots')
if os.path.exists(screenshots_dir):
    try:
        shutil.rmtree(screenshots_dir)
        os.makedirs(screenshots_dir)
        print("✅ Cleared old screenshots")
    except Exception as e:
        print(f"⚠️ Could not clear screenshots: {e}")

# Use startup timestamp as secret key - changes on every server restart
STARTUP_TIME = str(int(time.time()))
app.secret_key = STARTUP_TIME.encode()
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

print(f"✅ Server started at timestamp: {STARTUP_TIME}")

HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>IKEA Shopping Assistant</title>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
      * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
      }
      
      :root {
          --ikea-blue: #0058a3;
          --ikea-yellow: #ffdb00;
          --dark-blue: #003d73;
          --light-blue: #e1f5ff;
          --text-primary: #111111;
          --text-secondary: #666666;
          --background: #f5f5f5;
      }
      
      body {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%);
          height: 100vh;
          display: flex;
          justify-content: center;
          align-items: center;
          padding: 20px;
      }
      
      .chat-container {
          width: 100%;
          max-width: 1400px;
          height: 95vh;
          background: white;
          display: flex;
          flex-direction: column;
          border-radius: 16px;
          overflow: hidden;
          box-shadow: 0 20px 60px rgba(0,0,0,0.15);
      }
      
      .main-content {
          flex: 1;
          display: flex;
          overflow: hidden;
      }
      
      .chat-panel {
          flex: 1;
          display: flex;
          flex-direction: column;
          transition: all 0.3s ease;
      }
      
      .video-panel {
          width: 0;
          background: #f8f9fa;
          border-left: 1px solid #e0e0e0;
          overflow: hidden;
          transition: all 0.3s ease;
          display: flex;
          flex-direction: column;
      }
      
      .video-panel.active {
          width: 40%;
          min-width: 400px;
      }
      
      .video-panel-header {
          padding: 16px 20px;
          background: white;
          border-bottom: 1px solid #e0e0e0;
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-weight: 600;
          color: var(--text-primary);
      }
      
      .close-video-btn {
          width: 32px;
          height: 32px;
          border: none;
          background: #f5f5f5;
          border-radius: 50%;
          cursor: pointer;
          font-size: 18px;
          color: var(--text-secondary);
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
      }
      
      .close-video-btn:hover {
          background: var(--ikea-blue);
          color: white;
      }
      
      .video-content {
          flex: 1;
          padding: 20px;
          overflow-y: auto;
      }
      
      .header {
          background: linear-gradient(135deg, var(--ikea-blue) 0%, var(--dark-blue) 100%);
          color: white;
          padding: 20px 24px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
      }
      
      .header-title {
          font-size: 1.3em;
          font-weight: 600;
          letter-spacing: -0.5px;
      }
      
      .header-cart {
          position: relative;
          cursor: pointer;
          font-size: 24px;
      }

      .chat-box {
          flex: 1;
          padding: 24px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
          scroll-behavior: smooth;
          background: var(--background);
      }

      .message {
          max-width: 75%;
          padding: 14px 18px;
          border-radius: 18px;
          line-height: 1.5;
          position: relative;
          word-wrap: break-word;
          animation: slideIn 0.3s ease;
      }
      
      @keyframes slideIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
      }

      .user-message {
          align-self: flex-end;
          background: linear-gradient(135deg, var(--ikea-blue) 0%, #0066b8 100%);
          color: white;
          border-bottom-right-radius: 4px;
          box-shadow: 0 4px 12px rgba(0,88,163,0.25);
      }

      .bot-message {
          align-self: flex-start;
          background: white;
          color: var(--text-primary);
          border: 1px solid #e0e0e0;
          border-bottom-left-radius: 4px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.08);
          max-width: 90%;
      }
      
      .bot-avatar {
          width: 32px;
          height: 32px;
          background: var(--ikea-blue);
          border-radius: 50%;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          color: white;
          font-weight: 600;
          margin-right: 8px;
          vertical-align: middle;
      }
      
      /* Enhanced Product Card Styles */
      .product-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 20px;
          margin-top: 16px;
      }
      
      .product-card {
          background: white;
          border: 1px solid #e5e5e5;
          border-radius: 12px;
          overflow: hidden;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
      }
      
      .product-card:hover {
          transform: translateY(-4px);
          box-shadow: 0 12px 24px rgba(0,0,0,0.15);
          border-color: var(--ikea-blue);
      }
      
      .product-image {
          width: 100%;
          height: 180px;
          object-fit: cover;
          background: #fafafa;
          padding: 12px;
      }
      
      .product-info {
          padding: 16px;
      }
      
      .product-name {
          font-weight: 600;
          font-size: 0.95em;
          margin-bottom: 8px;
          color: var(--text-primary);
          min-height: 40px;
      }
      
      .product-rating {
          display: flex;
          align-items: center;
          gap: 6px;
          margin-bottom: 8px;
      }
      
      .stars {
          color: var(--ikea-yellow);
          font-size: 14px;
      }
      
      .rating-count {
          color: var(--text-secondary);
          font-size: 0.85em;
      }
      
      .product-price {
          color: var(--ikea-blue);
          font-weight: 700;
          font-size: 1.3em;
          margin-bottom: 12px;
      }
      
      .add-to-cart-btn {
          width: 100%;
          background: var(--ikea-yellow);
          color: var(--text-primary);
          border: none;
          padding: 12px;
          border-radius: 8px;
          font-weight: 600;
          font-size: 0.9em;
          cursor: pointer;
          transition: all 0.2s;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
      }
      
      .add-to-cart-btn:hover {
          background: #e6c400;
          transform: scale(1.02);
      }
      
      /* Video Container */
      .video-container {
          margin-top: 12px;
          border-radius: 12px;
          overflow: hidden;
          border: 1px solid #e0e0e0;
          background: #000;
          box-shadow: 0 4px 12px rgba(0,0,0,0.1);
      }
      
      .action-video {
          width: 100%;
          display: block;
      }

      .input-area {
          padding: 20px 24px;
          background: white;
          border-top: 1px solid #e5e5e5;
          flex-shrink: 0;
      }
      
      .quick-actions {
          display: flex;
          gap: 8px;
          margin-bottom: 12px;
          flex-wrap: wrap;
      }
      
      .quick-action-chip {
          padding: 8px 16px;
          background: var(--light-blue);
          color: var(--ikea-blue);
          border: 1px solid var(--ikea-blue);
          border-radius: 20px;
          font-size: 0.85em;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s;
      }
      
      .quick-action-chip:hover {
          background: var(--ikea-blue);
          color: white;
      }
      
      .input-row {
          display: flex;
          gap: 12px;
          align-items: center;
      }
      
      .voice-btn {
          width: 44px;
          height: 44px;
          background: var(--light-blue);
          border: none;
          border-radius: 50%;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          color: var(--ikea-blue);
          transition: all 0.2s;
          flex-shrink: 0;
      }
      
      .voice-btn:hover {
          background: var(--ikea-blue);
          color: white;
      }

      input[type="text"] {
          flex-grow: 1;
          padding: 14px 20px;
          border: 2px solid #e5e5e5;
          border-radius: 24px;
          outline: none;
          font-size: 15px;
          font-family: inherit;
          transition: all 0.3s;
      }
      
      input[type="text"]:focus {
          border-color: var(--ikea-blue);
          box-shadow: 0 0 0 3px rgba(0,88,163,0.1);
      }

      button[type="submit"] {
          width: 44px;
          height: 44px;
          padding: 0;
          background: var(--ikea-yellow);
          color: var(--text-primary);
          border: none;
          border-radius: 50%;
          cursor: pointer;
          font-weight: 600;
          font-size: 20px;
          transition: all 0.2s;
          flex-shrink: 0;
          display: flex;
          align-items: center;
          justify-content: center;
      }

      button[type="submit"]:hover {
          background: #e6c400;
          transform: scale(1.05);
      }
      
      /* Loading Indicator */
      .typing-indicator {
          display: none;
          align-self: flex-start;
          background: white;
          padding: 14px 18px;
          border-radius: 18px;
          border-bottom-left-radius: 4px;
          color: var(--text-secondary);
          font-style: italic;
          font-size: 0.9em;
          border: 1px solid #e0e0e0;
          box-shadow: 0 2px 8px rgba(0,0,0,0.08);
      }
      
      /* Responsive Design */
      @media (max-width: 768px) {
          .chat-container {
              height: 100vh;
              border-radius: 0;
          }
          
          .product-grid {
              grid-template-columns: 1fr;
          }
          
          .message {
              max-width: 85%;
          }
      }
  </style>
</head>
<body>
    <div class="chat-container">
        <div class="header">
            <div class="header-title">🛋️ IKEA Shopping Assistant</div>
            <div class="header-cart">🛒</div>
        </div>
        
        <div class="main-content">
            <!-- Chat Panel (always visible, flexes to fill space) -->
            <div class="chat-panel" id="chatPanel">
                <div class="chat-box" id="chatBox">
                    {% for message in history %}
                        <div class="message {{ 'user-message' if message.type == 'user' else 'bot-message' }}">
                            {% if message.type == 'agent' %}
                                <span class="bot-avatar">🏠</span>
                            {% endif %}
                            {{ message.content | safe }}
                        </div>
                    {% endfor %}
                    <div class="typing-indicator" id="typingIndicator">
                        Agent is thinking...
                    </div>
                </div>
                
                <div class="input-area">
                    <div class="quick-actions">
                        <div class="quick-action-chip" onclick="document.querySelector('input[name=\\'q\\']').value='show me office chairs';document.querySelector('form').submit()">Show chairs</div>
                        <div class="quick-action-chip" onclick="document.querySelector('input[name=\\'q\\']').value='view my cart';document.querySelector('form').submit()">View Cart</div>
                        <div class="quick-action-chip" onclick="document.querySelector('input[name=\\'q\\']').value='show chairs under $200';document.querySelector('form').submit()">Under $200</div>
                    </div>
                    
                    <form action="/" method="post" class="input-row" onsubmit="showTyping()">
                        <button type="button" class="voice-btn" title="Voice input">🎤</button>
                        <input type="text" name="q" placeholder="Ask about furniture..." required autocomplete="off" autofocus>
                        <button type="submit">↑</button>
                    </form>
                </div>
            </div>
            
            <!-- Video Panel (hidden by default, shows when video is available) -->
            <div class="video-panel" id="videoPanel">
                <div class="video-panel-header">
                    <span>🎥 Live Action</span>
                    <button class="close-video-btn" onclick="closeVideoPanel()" title="Close video panel">×</button>
                </div>
                <div class="video-content" id="videoContent">
                    <!-- Video content will be inserted here dynamically -->
                </div>
            </div>
        </div>
    </div>

    <script>
        // Auto-scroll to bottom
        const chatBox = document.getElementById('chatBox');
        chatBox.scrollTop = chatBox.scrollHeight;
        
        function showTyping() {
            document.getElementById('typingIndicator').style.display = 'block';
            chatBox.scrollTop = chatBox.scrollHeight;
        }
        
        // Video panel control functions
        function showVideoPanel(videoHtml) {
            const panel = document.getElementById('videoPanel');
            const content = document.getElementById('videoContent');
            
            // Set the video content
            content.innerHTML = videoHtml;
            
            // Add active class with small delay for smooth transition
            setTimeout(() => {
                panel.classList.add('active');
            }, 10);
        }
        
        function closeVideoPanel() {
            const panel = document.getElementById('videoPanel');
            panel.classList.remove('active');
        }
        
        // Check if there's video content in the latest message and show it in panel
        function checkForVideoContent() {
            const messages = document.querySelectorAll('.bot-message');
            if (messages.length > 0) {
                const lastMessage = messages[messages.length - 1];
                const videoElements = lastMessage.querySelectorAll('video');
                
                if (videoElements.length > 0) {
                    // Extract video HTML
                    const videoContainer = videoElements[0].closest('.video-container');
                    if (videoContainer) {
                        const videoHtml = videoContainer.outerHTML;
                        // Remove from message and show in panel
                        videoContainer.remove();
                        showVideoPanel(videoHtml);
                    }
                }
            }
        }
        
        // Run on page load
        checkForVideoContent();
        
        // Focus input on load
        document.querySelector('input[name="q"]').focus();
        
        // Voice input (placeholder for future implementation)
        document.querySelector('.voice-btn').addEventListener('click', function() {
            alert('Voice input coming soon!');
        });
    </script>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    # Check if session is from current server startup
    if session.get('_startup_time') != STARTUP_TIME:
        session.clear()
        session['_startup_time'] = STARTUP_TIME
    
    # Initialize session state if needed
    if 'history' not in session: session['history'] = []
    if 'messages' not in session: session['messages'] = []
    if 'last_products' not in session: session['last_products'] = []
    if 'cart_items' not in session: session['cart_items'] = []
    if 'pending_search_context' not in session: session['pending_search_context'] = None
    
    if request.method == 'POST':
        query = request.form.get('q', '')
        if query:
            session['history'].append({'type': 'user', 'content': query})
            
            # Run agent
            response, updated_messages, updated_products, updated_cart, updated_pending = handle_query(
                query,
                session['messages'],
                session['last_products'],
                session['cart_items'],
                session['pending_search_context']
            )
            
            try:
                html_response = markdown.markdown(response, extensions=['tables', 'fenced_code', 'md_in_html'], extension_configs={'md_in_html': {'raw_html': True}})
            except Exception:
                html_response = response
            
            session['messages'] = updated_messages
            session['last_products'] = updated_products
            session['cart_items'] = updated_cart
            session['pending_search_context'] = updated_pending
            session['history'].append({'type': 'agent', 'content': html_response})
            session.modified = True
    
    return render_template_string(HTML, history=session.get('history', []))

@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screenshots')
    return send_from_directory(screenshots_dir, filename)

@app.route('/videos/<path:filename>')
def serve_video(filename):
    videos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'videos')
    return send_from_directory(videos_dir, filename)

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
