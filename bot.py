"""
Telegram Bot Handlers
Handles all incoming messages and forwards them to processing
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import logging
from typing import Optional
from models import Memory
from database import get_db_session
from ai_engine import AIEngine
from search import SearchEngine
from config import Config
import requests
from bs4 import BeautifulSoup
import io
from PIL import Image

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot for MyMindIL"""
    
    def __init__(self, token: str, webhook_url: Optional[str] = None):
        self.token = token
        self.webhook_url = webhook_url
        self.app = Application.builder().token(token).build()
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all message handlers"""
        # Commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("search", self.search_command))
        
        # Message types
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        self.app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.app.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        self.app.add_handler(MessageHandler(filters.Entity("url"), self.handle_link))
        
        logger.info("Bot handlers registered")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        
        # Create Web App button
        web_app_url = self.webhook_url.replace('/webhook', '') if self.webhook_url else 'https://yourdomain.com'
        keyboard = [
            [InlineKeyboardButton(
                "🔍 פתח את הארכיון",
                web_app=WebAppInfo(url=web_app_url)
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = f"""
שלום {user.first_name}! 👋

ברוכים הבאים ל-MyMindIL - המוח השני שלך בטלגרם.

🎯 איך זה עובד?
• העבר אליי כל הודעה שתרצה לשמור
• אני אשמור אותה עם חיפוש חכם
• תוכל למצוא הכל בקלות בעזרת חיפוש סמנטי

💡 מה אפשר לשמור?
✅ טקסט חופשי ורעיונות
✅ תמונות וצילומי מסך
✅ הקלטות קול
✅ קישורים ומאמרים
✅ חשבוניות ומסמכים

🔍 לחפש בארכיון - לחץ על הכפתור למטה
📊 סטטיסטיקות - /stats
❓ עזרה - /help

שלח לי משהו לנסות! 🚀
"""
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📚 מדריך שימוש ב-MyMindIL

🎯 פקודות זמינות:
/start - התחל מחדש
/help - המדריך הזה
/stats - סטטיסטיקות על הזיכרונות שלך
/search <חיפוש> - חפש בזיכרונות

💾 שמירת תוכן:
פשוט העבר (Forward) או שלח הודעה:
• טקסט - כל מחשבה או רעיון
• תמונה - צילום מסך, חשבונית, תמונה
• הקלטה - הקלטת קול שתרצה לזכור
• קישור - מאמר או אתר מעניין

🔍 חיפוש:
השתמש באפליקציה לחיפוש חכם:
• חפש לפי תוכן סמנטי
• סנן לפי תאריך, קטגוריה, תגיות
• מצא חשבוניות לפי סכום או ספק

💡 טיפים:
• המערכת מבינה עברית באופן מלא
• תוכל לחפש גם במילים שלא הופיעו במקור
• השתמש בשפה טבעית ("החשבונית מהמוסך")

זקוק לעזרה נוספת? שלח הודעה עם השאלה שלך.
"""
        await update.message.reply_text(help_text)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        user_id = update.effective_user.id
        
        try:
            stats = SearchEngine.get_memory_stats(user_id)
            
            stats_text = f"""
📊 הסטטיסטיקות שלך

📝 סה"כ זיכרונות: {stats['total_memories']}

📂 לפי סוג:
"""
            
            type_names = {
                'text': '📄 טקסט',
                'image': '🖼 תמונות',
                'voice': '🎤 הקלטות',
                'link': '🔗 קישורים'
            }
            
            for content_type, count in stats['by_type'].items():
                name = type_names.get(content_type, content_type)
                stats_text += f"{name}: {count}\n"
            
            if stats['by_category']:
                stats_text += "\n🏷 קטגוריות פופולריות:\n"
                for category, count in list(stats['by_category'].items())[:5]:
                    stats_text += f"• {category}: {count}\n"
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            await update.message.reply_text("❌ שגיאה בטעינת הסטטיסטיקות")
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /search command"""
        user_id = update.effective_user.id
        
        # Extract query from command
        query = ' '.join(context.args) if context.args else None
        
        if not query:
            await update.message.reply_text(
                "🔍 שימוש: /search <מה לחפש>\n"
                "לדוגמה: /search חשבוניות מהחודש האחרון"
            )
            return
        
        try:
            results = SearchEngine.search(user_id, query, limit=5)
            
            if not results:
                await update.message.reply_text("😕 לא נמצאו תוצאות")
                return
            
            response = f"🔍 נמצאו {len(results)} תוצאות עבור '{query}':\n\n"
            
            for i, memory in enumerate(results, 1):
                similarity = memory.get('similarity', 0)
                response += f"{i}. {memory['display_text']}\n"
                response += f"   📅 {memory['created_at'][:10]} | דירוג: {similarity:.2f}\n\n"
            
            response += "💡 לחיפוש מתקדם - השתמש באפליקציה"
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            await update.message.reply_text("❌ שגיאה בחיפוש")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user_id = update.effective_user.id
        text = update.message.text
        
        try:
            # Send "processing" message
            status_msg = await update.message.reply_text("⏳ שומר...")
            
            # Analyze with AI
            analysis = AIEngine.analyze_content(text, content_type='text')
            
            # Generate embedding
            embedding_text = f"{analysis['display_text']} {analysis['search_text']}"
            embedding = AIEngine.generate_embedding(embedding_text)
            
            # Save to database
            with get_db_session() as session:
                memory = Memory(
                    user_id=user_id,
                    content_type='text',
                    original_content=text,
                    display_text=analysis['display_text'],
                    search_text=analysis['search_text'],
                    meta=analysis['metadata'],
                    embedding=embedding
                )
                session.add(memory)
            
            # Update status message
            await status_msg.edit_text(
                f"✅ נשמר!\n\n"
                f"📝 {analysis['display_text']}\n\n"
                f"🏷 {', '.join(analysis['metadata'].get('tags', [])[:3])}"
            )
            
            logger.info(f"Saved text memory for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle text: {e}")
            await update.message.reply_text("❌ שגיאה בשמירת ההודעה")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo messages"""
        user_id = update.effective_user.id
        caption = update.message.caption or ""
        
        try:
            status_msg = await update.message.reply_text("⏳ מעבד תמונה...")
            
            # Get the largest photo
            photo = update.message.photo[-1]
            file = await photo.get_file()
            
            # Download photo
            photo_bytes = await file.download_as_bytearray()
            
            # Analyze with AI (including vision)
            analysis = AIEngine.analyze_content(
                caption,
                content_type='image',
                image_data=bytes(photo_bytes)
            )
            
            # Generate embedding
            embedding_text = f"{analysis['display_text']} {analysis['search_text']}"
            embedding = AIEngine.generate_embedding(embedding_text)
            
            # Save to database
            with get_db_session() as session:
                memory = Memory(
                    user_id=user_id,
                    content_type='image',
                    original_content=photo.file_id,  # Store Telegram file_id
                    display_text=analysis['display_text'],
                    search_text=analysis['search_text'],
                    meta=analysis['metadata'],
                    embedding=embedding
                )
                session.add(memory)
            
            await status_msg.edit_text(
                f"✅ תמונה נשמרה!\n\n"
                f"🖼 {analysis['display_text']}\n\n"
                f"🏷 {', '.join(analysis['metadata'].get('tags', [])[:3])}"
            )
            
            logger.info(f"Saved image memory for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle photo: {e}")
            await update.message.reply_text("❌ שגיאה בשמירת התמונה")
    
    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages"""
        user_id = update.effective_user.id
        
        try:
            status_msg = await update.message.reply_text("⏳ מעבד הקלטה...")
            
            voice = update.message.voice
            
            # For MVP, we'll save the file_id
            # In production, you might want to transcribe using Google Speech-to-Text
            
            placeholder_text = f"הקלטת קול ({voice.duration} שניות)"
            
            # Basic analysis without transcription
            analysis = {
                'display_text': placeholder_text,
                'search_text': 'הקלטת קול',
                'metadata': {
                    'duration': voice.duration,
                    'category': 'voice_memo',
                    'tags': ['הקלטה', 'קול']
                }
            }
            
            embedding = AIEngine.generate_embedding(analysis['search_text'])
            
            with get_db_session() as session:
                memory = Memory(
                    user_id=user_id,
                    content_type='voice',
                    original_content=voice.file_id,
                    display_text=analysis['display_text'],
                    search_text=analysis['search_text'],
                    meta=analysis['metadata'],
                    embedding=embedding
                )
                session.add(memory)
            
            await status_msg.edit_text(f"✅ הקלטה נשמרה! ({voice.duration} שניות)")
            
            logger.info(f"Saved voice memory for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle voice: {e}")
            await update.message.reply_text("❌ שגיאה בשמירת ההקלטה")
    
    async def handle_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages with links"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Extract first URL
        entities = update.message.entities or []
        url = None
        for entity in entities:
            if entity.type == "url":
                url = text[entity.offset:entity.offset + entity.length]
                break
        
        if not url:
            return await self.handle_text(update, context)
        
        try:
            status_msg = await update.message.reply_text("⏳ מוריד קישור...")
            
            # Scrape link content
            try:
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; MyMindIL/1.0)'
                })
                soup = BeautifulSoup(response.content, 'html.parser')
                
                title = soup.find('title')
                title_text = title.get_text() if title else ""
                
                # Get meta description
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                description = meta_desc.get('content', '') if meta_desc else ""
                
                link_content = f"{title_text}\n{description}\n{text}"
                
            except Exception as e:
                logger.warning(f"Failed to scrape URL: {e}")
                link_content = text
            
            # Analyze
            analysis = AIEngine.analyze_content(link_content, content_type='link')
            
            # Add URL to metadata
            analysis['metadata']['url'] = url
            
            embedding_text = f"{analysis['display_text']} {analysis['search_text']}"
            embedding = AIEngine.generate_embedding(embedding_text)
            
            with get_db_session() as session:
                memory = Memory(
                    user_id=user_id,
                    content_type='link',
                    original_content=url,
                    display_text=analysis['display_text'],
                    search_text=analysis['search_text'],
                    meta=analysis['metadata'],
                    embedding=embedding
                )
                session.add(memory)
            
            await status_msg.edit_text(
                f"✅ קישור נשמר!\n\n"
                f"🔗 {analysis['display_text']}\n\n"
                f"🏷 {', '.join(analysis['metadata'].get('tags', [])[:3])}"
            )
            
            logger.info(f"Saved link memory for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle link: {e}")
            await update.message.reply_text("❌ שגיאה בשמירת הקישור")
    
    async def setup_webhook(self):
        """Setup webhook for production"""
        if self.webhook_url:
            await self.app.bot.set_webhook(
                url=f"{self.webhook_url}",
                allowed_updates=Update.ALL_TYPES
            )
            logger.info(f"Webhook set to {self.webhook_url}")
    
    def run_polling(self):
        """Run bot in polling mode (development)"""
        logger.info("Starting bot in polling mode...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def get_application(self):
        """Get the application instance for webhook mode"""
        return self.app
