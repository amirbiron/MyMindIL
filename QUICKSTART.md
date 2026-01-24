# MyMindIL - Quick Start Guide

## מה יש בפרויקט?

✅ **14 קבצים מוכנים לייצור**:

### Core Files (7)
1. `app.py` - Flask application + API endpoints
2. `bot.py` - Telegram bot handlers
3. `database.py` - PostgreSQL + pgvector management
4. `models.py` - SQLAlchemy ORM models
5. `ai_engine.py` - Gemini AI wrapper
6. `search.py` - Hybrid search engine
7. `config.py` - Configuration management

### Frontend (1)
8. `templates/index.html` - Telegram Web App UI (Pinterest style)

### Configuration (3)
9. `requirements.txt` - Python dependencies
10. `.env.example` - Environment variables template
11. `Procfile` - Render deployment config

### Documentation (3)
12. `README.md` - Full project documentation
13. `DEPLOYMENT.md` - Step-by-step deployment guide
14. `.gitignore` - Git ignore rules

## התחלה מהירה (5 דקות)

### שלב 1: הורד והתקן
```bash
# פרוס את הארכיב
tar -xzf mymindil.tar.gz
cd mymindil

# צור סביבה וירטואלית
python -m venv venv
source venv/bin/activate

# התקן תלויות
pip install -r requirements.txt
```

### שלב 2: הגדרות
```bash
# העתק ועדכן
cp .env.example .env
nano .env  # או כל עורך טקסט

# השלם:
# - DATABASE_URL (מ-Supabase/Neon)
# - TELEGRAM_TOKEN (מ-@BotFather)
# - GOOGLE_API_KEY (מ-Google AI Studio)
```

### שלב 3: הרץ
```bash
# Development mode (polling)
python app.py

# Production mode (webhook) - ב-Render
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
```

## תכונות מובנות

### 🤖 AI Features
- ✅ Gemini 1.5 Flash לניתוח תוכן
- ✅ חילוץ מטא-דאטה אוטומטי (JSON)
- ✅ סיווג לקטגוריות
- ✅ זיהוי ישויות (NER)
- ✅ ניתוח סנטימנט
- ✅ תיוג אוטומטי

### 🔍 Search Features
- ✅ חיפוש סמנטי (vector similarity)
- ✅ חיפוש מילות מפתח
- ✅ סינון לפי metadata
- ✅ פגינציה
- ✅ חיפוש לפי סוג תוכן
- ✅ תמיכה מלאה בעברית

### 📱 Bot Features
- ✅ קליטת טקסט
- ✅ קליטת תמונות + Vision AI
- ✅ קליטת הקלטות קול
- ✅ קליטת לינקים + scraping
- ✅ פקודות: /start, /help, /stats, /search
- ✅ Inline feedback

### 🌐 Web App Features
- ✅ Pinterest-style masonry grid
- ✅ RTL support (עברית)
- ✅ Telegram theme integration
- ✅ סינון לפי סוג
- ✅ חיפוש real-time
- ✅ Modal לפרטים מלאים
- ✅ Responsive design

### 💾 Database Features
- ✅ PostgreSQL 15+
- ✅ pgvector extension
- ✅ HNSW index (מהיר!)
- ✅ GIN index על JSONB
- ✅ Connection pooling
- ✅ Migration support

### 🛡 Production Ready
- ✅ Error handling
- ✅ Logging
- ✅ Health checks
- ✅ Metrics endpoint
- ✅ Sentry integration
- ✅ Environment-based config
- ✅ SQL injection protection

## Architecture Overview

```
┌──────────────┐
│   Telegram   │ ← משתמשים
│     Bot      │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│    Flask     │ ← Webhook + Web App
│  Application │
└──────┬───────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
┌────────────┐  ┌──────────┐
│   Gemini   │  │PostgreSQL│
│  AI API    │  │+pgvector │
└────────────┘  └──────────┘
```

## Stack Tecnológico

### Backend
- Python 3.11+
- Flask 3.0
- SQLAlchemy 2.0
- python-telegram-bot 21.0
- google-generativeai 0.3+

### Database
- PostgreSQL 15+
- pgvector 0.2+

### AI
- Gemini 1.5 Flash (analysis)
- text-embedding-004 (768d vectors)

### Frontend
- Vanilla JavaScript
- Tailwind CSS
- Telegram Web App SDK

### Deployment
- Render (recommended)
- Gunicorn (WSGI)
- Supabase/Neon (DB)

## API Endpoints

```
POST /webhook              # Telegram webhook
GET  /                     # Web App UI
POST /api/search          # Semantic search
GET  /api/stats           # User statistics
GET  /api/recent          # Recent memories
GET  /health              # Health check
GET  /metrics             # Monitoring
```

## Environment Variables

```bash
# Required
DATABASE_URL=postgresql://...
TELEGRAM_TOKEN=123456:ABC...
GOOGLE_API_KEY=AIza...

# Optional
SECRET_KEY=...              # Flask secret
TELEGRAM_WEBHOOK_URL=...    # Production only
SENTRY_DSN=...             # Error tracking
REDIS_URL=...              # Caching
DEBUG=False                # Development only
```

## Performance

### Benchmarks (Expected)
- Search latency: <200ms (semantic)
- Ingestion: <2s (with AI)
- Concurrent users: 100+ (2 workers)
- Database: 1M+ memories

### Scaling
- Horizontal: Add Render workers
- Vertical: Upgrade instance type
- Database: Connection pool (5-10)
- Redis: Add caching layer

## Security Checklist

- [x] Environment variables for secrets
- [x] SQL injection protection (ORM)
- [x] HTTPS only (webhook)
- [x] Telegram user validation
- [x] Input sanitization
- [x] Error logging (Sentry)
- [ ] Rate limiting (optional)
- [ ] API authentication (optional)

## Next Steps

### Immediate
1. קרא את README.md המלא
2. עקוב אחרי DEPLOYMENT.md לפריסה
3. בדוק health endpoint
4. נסה את הבוט

### Future Enhancements
- [ ] Voice transcription (Google Speech-to-Text)
- [ ] Image OCR
- [ ] Redis caching
- [ ] Rate limiting
- [ ] User analytics
- [ ] Export functionality
- [ ] Sharing capabilities
- [ ] Advanced filters

## Support

- 📖 Read: README.md (מפורט)
- 🚀 Deploy: DEPLOYMENT.md (צעד אחר צעד)
- 🐛 Issues: בדוק logs ב-/health
- 💬 Questions: פתח issue

---

**בהצלחה! 🎉**
