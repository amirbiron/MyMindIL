# MyMindIL 🧠 - המוח השני שלך בטלגרם

בוט "שמור הכל" מתקדם לטלגרם עם חיפוש סמנטי חכם, בסגנון MyMind. שמור טקסט, תמונות, הקלטות ולינקים - ומצא הכל בקלות עם AI.

## ✨ תכונות

- 📥 **קליטה אוטומטית**: העבר כל הודעה והיא נשמרת אוטומטית
- 🤖 **AI חכם**: Gemini 1.5 Flash מנתח ומסווג את התוכן
- 🔍 **חיפוש סמנטי**: מצא תוכן לפי משמעות, לא רק מילים מדויקות
- 🎨 **ממשק מהמם**: Web App בסגנון Pinterest עם תמיכה מלאה בעברית
- 📊 **מטא-דאטה מובנית**: סכומים, תאריכים, קטגוריות, תגיות ועוד
- ⚡ **ביצועים גבוהים**: PostgreSQL + pgvector לחיפוש מהיר

## 🏗 אריכטקטורה

```
┌─────────────────┐
│  Telegram Bot   │  ← משתמשים שולחים תוכן
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   AI Engine     │  ← Gemini 1.5 Flash + Embeddings
│  (Gemini API)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  PostgreSQL +   │  ← אחסון + חיפוש וקטורי
│    pgvector     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Telegram Web   │  ← ממשק חיפוש
│      App        │
└─────────────────┘
```

## 🚀 התקנה והפעלה

### דרישות מקדימות

1. **Python 3.11+**
2. **PostgreSQL 15+** עם התוסף pgvector (Supabase/Neon מומלצים)
3. **Telegram Bot Token** - קבל מ-[@BotFather](https://t.me/botfather)
4. **Google AI API Key** - קבל מ-[Google AI Studio](https://makersuite.google.com/app/apikey)

### שלב 1: הכנת הסביבה

```bash
# שכפל את הפרויקט
git clone <your-repo-url>
cd mymindil

# צור סביבה וירטואלית
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# התקן תלויות
pip install -r requirements.txt
```

### שלב 2: הגדרות

```bash
# העתק את קובץ הדוגמה
cp .env.example .env

# ערוך את .env והשלם:
# - DATABASE_URL (מ-Supabase/Neon)
# - TELEGRAM_TOKEN
# - GOOGLE_API_KEY
```

### שלב 3: אתחול מסד נתונים

הפרויקט יוצר אוטומטית את הטבלאות והאינדקסים בהפעלה הראשונה.

אם אתה משתמש ב-Supabase:
```sql
-- הפעל ב-SQL Editor של Supabase
CREATE EXTENSION IF NOT EXISTS vector;
```

### שלב 4: הפעלה מקומית (פיתוח)

```bash
# ללא webhook (polling mode)
python app.py
```

הבוט יתחיל לעבוד ב-polling mode והשרת יהיה זמין ב-`http://localhost:5000`

### שלב 5: בדיקה

1. שלח הודעה לבוט בטלגרם
2. הבוט יענה עם אישור
3. פתח `http://localhost:5000` בדפדפן לראות את הממשק

## 🌐 פריסה ל-Production (Render)

### שלב 1: הכנת הפרויקט

צור קובץ `render.yaml`:

```yaml
services:
  - type: web
    name: mymindil
    env: python
    region: frankfurt  # או כל region קרוב
    plan: starter
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      - key: DATABASE_URL
        sync: false
      - key: TELEGRAM_TOKEN
        sync: false
      - key: GOOGLE_API_KEY
        sync: false
      - key: SECRET_KEY
        generateValue: true
      - key: TELEGRAM_WEBHOOK_URL
        value: https://YOUR-APP-NAME.onrender.com/webhook
```

### שלב 2: הגדרת Database

#### אופציה א': Supabase (מומלץ)

1. צור פרויקט ב-[Supabase](https://supabase.com)
2. עבור ל-SQL Editor והרץ:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
3. העתק את ה-Connection String (Transaction mode)
4. הוסף ל-Render כ-Environment Variable

#### אופציה ב': Neon

1. צור database ב-[Neon](https://neon.tech)
2. הפעל את pgvector דרך הקונסולה
3. העתק את ה-Connection String
4. הוסף ל-Render כ-Environment Variable

### שלב 3: פריסה ל-Render

```bash
# התחבר ל-Render מה-CLI או דרך הממשק
render deploy
```

או:
1. צור Repository ב-GitHub
2. חבר את ה-Repository ל-Render
3. Render יפעיל אוטומטית

### שלב 4: הגדרת Webhook

לאחר הפריסה:

```bash
# הגדר את ה-webhook URL
export TELEGRAM_WEBHOOK_URL=https://YOUR-APP.onrender.com/webhook

# הפעל מחדש את השירות
```

או הגדר ישירות ב-Render Dashboard → Environment Variables

### שלב 5: בדיקת Health

```bash
# בדוק שהשרת עובד
curl https://YOUR-APP.onrender.com/health

# אמור להחזיר:
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

## 📊 ניטור ותחזוקה

### Health Checks

```bash
# בריאות כללית
GET /health

# מטריקות
GET /metrics
```

### לוגים

ב-Render:
```bash
render logs -t <service-id>
```

### Sentry (אופציונלי)

להוסיף מעקב שגיאות:
```bash
# הוסף ל-.env
SENTRY_DSN=your-sentry-dsn
```

## 🔧 API Documentation

### POST /api/search
חיפוש סמנטי בזיכרונות

```json
{
  "user_id": 123456789,
  "query": "חשבוניות מהמוסך",
  "limit": 20,
  "offset": 0,
  "filters": {
    "category": "invoice"
  }
}
```

### GET /api/stats
סטטיסטיקות משתמש

```bash
GET /api/stats?user_id=123456789
```

### GET /api/recent
זיכרונות אחרונים

```bash
GET /api/recent?user_id=123456789&limit=20&content_type=image
```

## 🎯 שימוש

### פקודות בוט

- `/start` - התחלה והצגת הממשק
- `/help` - מדריך שימוש
- `/stats` - סטטיסטיקות
- `/search <שאילתא>` - חיפוש מהיר

### סוגי תוכן נתמכים

| סוג | אייקון | תיאור |
|-----|--------|--------|
| טקסט | 📄 | כל טקסט חופשי, רעיונות, משימות |
| תמונה | 🖼 | צילומי מסך, חשבוניות, תמונות |
| הקלטה | 🎤 | הקלטות קול (תמלול בגרסה עתידית) |
| קישור | 🔗 | מאמרים, אתרים, משאבים |

### דוגמאות חיפוש

```
"החשבונית מהמוסך"
"רעיונות לפרויקט החדש"
"תמונות מהחופשה"
"המאמר על AI שקראתי"
"משימות דחופות"
```

## 🛠 פיתוח

### מבנה הפרויקט

```
mymindil/
├── app.py              # Flask application + webhook
├── bot.py              # Telegram bot handlers
├── database.py         # Database connection & session
├── models.py           # SQLAlchemy models
├── ai_engine.py        # Gemini API wrapper
├── search.py           # Search engine
├── config.py           # Configuration
├── requirements.txt    # Dependencies
├── templates/
│   └── index.html     # Web App UI
└── README.md
```

### הרצת Tests

```bash
# יחידה (להוסיף)
pytest tests/

# Integration
python -m pytest tests/integration/
```

### Code Quality

```bash
# Linting
flake8 .

# Type checking
mypy .

# Format
black .
```

## 🔐 אבטחה

- ✅ Environment variables לסודות
- ✅ SQL Injection protection (SQLAlchemy)
- ✅ Rate limiting (אופציונלי עם Redis)
- ✅ HTTPS only (webhook)
- ✅ Telegram user validation

## 📈 אופטימיזציה

### Database Indexes

הפרויקט יוצר אוטומטית:
- HNSW index על embeddings (חיפוש וקטורי מהיר)
- GIN index על metadata (חיפוש JSON)
- B-Tree על user_id + created_at

### Caching (עתידי)

```python
# Redis caching לשאילתות פופולריות
REDIS_URL=redis://...
```

### Scaling

- **Horizontal**: הוסף workers ל-Render
- **Vertical**: שדרג plan ב-Render
- **Database**: Connection pooling מובנה

## 🐛 פתרון בעיות

### הבוט לא עונה

```bash
# בדוק webhook
curl -X POST https://api.telegram.org/bot<TOKEN>/getWebhookInfo

# אפס webhook
curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook
```

### שגיאות Database

```python
# בדוק חיבור
python -c "from database import check_db_connection; print(check_db_connection())"

# אפס טבלאות (זהירות!)
python -c "from database import Base, engine; Base.metadata.drop_all(engine); Base.metadata.create_all(engine)"
```

### AI לא עובד

```bash
# בדוק API key
curl -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"test"}]}]}' \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=YOUR_KEY"
```

## 📝 License

MIT License - ראה LICENSE לפרטים

## 🤝 תרומה

Pull requests מתקבלים בברכה! לשינויים גדולים, פתח issue קודם.

## 📧 יצירת קשר

נוצר על ידי אמיר חיים
- Telegram: [@your_username](https://t.me/your_username)

---

**הערה**: זהו MVP מוכן לייצור. לסקלה גדולה יותר, שקול:
- Redis לקאשינג
- Celery לתורים
- Kubernetes לאורקסטרציה
- CDN לקבצי מדיה
