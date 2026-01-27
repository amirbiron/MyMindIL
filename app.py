"""
Main Flask Application for MyMindIL
Serves the Telegram Web App and API endpoints
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
from telegram import Update
import asyncio
import logging
import os
import threading
from config import Config
from database import init_db, check_db_connection, get_db_stats
from bot import TelegramBot
from search import SearchEngine
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize bot
bot_instance: Optional[TelegramBot] = None
_init_lock = threading.Lock()
_app_initialized = False


def init_app():
    """Initialize application components"""
    global bot_instance
    
    # Validate configuration
    Config.validate()
    logger.info("Configuration validated")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    # Initialize bot
    bot_instance = TelegramBot(
        token=Config.TELEGRAM_TOKEN,
        webhook_url=Config.TELEGRAM_WEBHOOK_URL
    )
    logger.info("Bot initialized")
    
    return bot_instance


def ensure_initialized():
    """Ensure the application and bot are initialized once."""
    global _app_initialized, bot_instance
    if _app_initialized:
        return
    with _init_lock:
        if _app_initialized:
            return
        bot_instance = init_app()
        _app_initialized = True


def ensure_webhook():
    """Ensure webhook is set in production environments."""
    if Config.TELEGRAM_WEBHOOK_URL:
        try:
            setup_webhook_async()
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")


# ============================================================================
# Web App Routes
# ============================================================================

@app.route('/')
def index():
    """Serve the main Telegram Web App interface"""
    return render_template('index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


# ============================================================================
# API Routes
# ============================================================================

@app.route('/api/search', methods=['POST'])
def api_search():
    """
    Search endpoint for the web app
    
    Request JSON:
    {
        "user_id": 123456,
        "query": "חשבוניות מהמוסך",
        "limit": 20,
        "offset": 0,
        "filters": {"category": "invoice"}  // optional
    }
    
    Response JSON:
    {
        "success": true,
        "results": [...],
        "total": 5
    }
    """
    try:
        data = request.get_json()
        
        user_id = data.get('user_id')
        query = data.get('query', '')
        limit = min(data.get('limit', 20), 50)  # Max 50 results
        offset = data.get('offset', 0)
        filters = data.get('filters')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id required'}), 400
        
        if not query:
            # Return recent memories if no query
            results = SearchEngine.get_recent_memories(
                user_id=user_id,
                limit=limit,
                offset=offset
            )
        else:
            # Perform semantic search
            results = SearchEngine.search(
                user_id=user_id,
                query=query,
                limit=limit,
                offset=offset,
                filters=filters
            )
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results)
        })
        
    except Exception as e:
        logger.error(f"Search API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """
    Get user statistics
    
    Query params:
        user_id: Telegram user ID
    
    Response JSON:
    {
        "success": true,
        "stats": {...}
    }
    """
    try:
        user_id = request.args.get('user_id', type=int)
        
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id required'}), 400
        
        stats = SearchEngine.get_memory_stats(user_id)
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Stats API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/recent', methods=['GET'])
def api_recent():
    """
    Get recent memories
    
    Query params:
        user_id: Telegram user ID
        limit: Number of results (default 20)
        offset: Pagination offset (default 0)
        content_type: Optional filter (text/image/voice/link)
    """
    try:
        user_id = request.args.get('user_id', type=int)
        limit = min(request.args.get('limit', 20, type=int), 50)
        offset = request.args.get('offset', 0, type=int)
        content_type = request.args.get('content_type')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'user_id required'}), 400
        
        results = SearchEngine.get_recent_memories(
            user_id=user_id,
            limit=limit,
            offset=offset,
            content_type=content_type
        )
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results)
        })
        
    except Exception as e:
        logger.error(f"Recent API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# Telegram Webhook Route
# ============================================================================

@app.route('/webhook', methods=['POST'])
async def webhook():
    """
    Telegram webhook endpoint
    Receives updates from Telegram and processes them
    """
    try:
        if bot_instance is None:
            ensure_initialized()
        update = Update.de_json(request.get_json(), bot_instance.app.bot)
        await bot_instance.app.process_update(update)
        return jsonify({'ok': True})
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


# ============================================================================
# Health & Monitoring Routes
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for monitoring"""
    db_ok = check_db_connection()
    
    return jsonify({
        'status': 'healthy' if db_ok else 'unhealthy',
        'database': 'connected' if db_ok else 'disconnected',
        'version': '1.0.0'
    }), 200 if db_ok else 503


@app.route('/metrics', methods=['GET'])
def metrics():
    """Metrics endpoint for monitoring"""
    try:
        db_stats = get_db_stats()
        
        return jsonify({
            'database': db_stats,
            'application': {
                'uptime': 'N/A',  # Add uptime tracking if needed
            }
        })
        
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================================
# Application Entry Point
# ============================================================================

def setup_webhook_async():
    """Setup webhook asynchronously"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_instance.setup_webhook())
    loop.close()


def bootstrap_app():
    """Initialize components for WSGI servers like gunicorn."""
    ensure_initialized()
    ensure_webhook()


bootstrap_app()


if __name__ == '__main__':
    # Initialize app
    bootstrap_app()
    
    # Check if running in webhook or polling mode
    if Config.TELEGRAM_WEBHOOK_URL:
        # Production mode - webhook
        logger.info("Running in WEBHOOK mode")
        
        # Run Flask app (use gunicorn in production)
        app.run(
            host='0.0.0.0',
            port=int(os.getenv('PORT', 5000)),
            debug=Config.DEBUG
        )
    else:
        # Development mode - polling
        logger.info("Running in POLLING mode")
        
        # Run Flask in a separate thread
        from threading import Thread
        flask_thread = Thread(
            target=lambda: app.run(host='0.0.0.0', port=5000, debug=False)
        )
        flask_thread.daemon = True
        flask_thread.start()
        
        # Run bot in polling mode
        bot_instance.run_polling()
