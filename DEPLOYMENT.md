# מדריך פריסה ל-Render - צעד אחר צעד

## שלב 1: הכנת Database (Supabase)

### 1.1 יצירת פרויקט
1. היכנס ל-[Supabase](https://supabase.com)
2. לחץ על "New Project"
3. בחר שם: `mymindil-db`
4. בחר סיסמה חזקה ושמור אותה
5. בחר region קרוב (Frankfurt מומלץ)
6. המתן לסיום ההקמה (~2 דקות)

### 1.2 הפעלת pgvector
1. עבור ל-SQL Editor (מהתפריט הצדדי)
2. הרץ את הפקודה:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
3. לחץ RUN

### 1.3 העתקת Connection String
1. עבור ל-Settings → Database
2. גלול ל-"Connection string"
3. בחר "Transaction pooling"
4. העתק את ה-URL (מתחיל ב-`postgresql://...`)
5. שמור בצד

## שלב 2: הכנת Bot בטלגרם

### 2.1 יצירת Bot
1. פתח שיחה עם [@BotFather](https://t.me/botfather)
2. שלח `/newbot`
3. בחר שם: `MyMindIL Bot`
4. בחר username: `mymindil_bot` (צריך להיות זמין)
5. שמור את ה-Token שמקבלים

### 2.2 הגדרות נוספות
```
/setdescription - שמור הכל, מצא הכל
/setabouttext - בוט מוח שני חכם עם AI
/setuserpic - העלה לוגו (אופציונלי)
```

## שלב 3: Google AI API Key

### 3.1 קבלת API Key
1. היכנס ל-[Google AI Studio](https://makersuite.google.com/app/apikey)
2. לחץ "Get API Key"
3. בחר פרויקט קיים או צור חדש
4. העתק את המפתח
5. שמור בצד

## שלב 4: פריסה ל-Render

### 4.1 הכנת הקוד
```bash
# צור repository ב-GitHub
git init
git add .
git commit -m "Initial commit - MyMindIL MVP"
git remote add origin https://github.com/YOUR-USERNAME/mymindil.git
git push -u origin main
```

### 4.2 חיבור ל-Render
1. היכנס ל-[Render](https://render.com)
2. לחץ "New +" → "Web Service"
3. חבר את ה-GitHub repository
4. הגדרות:
   - Name: `mymindil`
   - Region: Frankfurt (או קרוב)
   - Branch: `main`
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

### 4.3 Environment Variables
הוסף את המשתנים הבאים (Settings → Environment):

```
DATABASE_URL = [מ-Supabase שלב 1.3]
TELEGRAM_TOKEN = [מ-BotFather שלב 2.1]
GOOGLE_API_KEY = [מ-Google AI שלב 3.1]
SECRET_KEY = [מחרוזת אקראית - Render יכול לייצר]
TELEGRAM_WEBHOOK_URL = https://YOUR-APP-NAME.onrender.com/webhook
```

**חשוב**: 
- החלף `YOUR-APP-NAME` בשם האפליקציה שבחרת ב-Render
- אם שם האפליקציה הוא `mymindil`, ה-URL יהיה:
  `https://mymindil.onrender.com/webhook`

### 4.4 Deploy
1. לחץ "Create Web Service"
2. המתן לבנייה (~5 דקות)
3. אם הכל תקין - תראה "Live" בירוק

## שלב 5: בדיקה

### 5.1 בדיקת Health
```bash
curl https://YOUR-APP-NAME.onrender.com/health
```

אמור להחזיר:
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

### 5.2 בדיקת Bot
1. פתח את הבוט בטלגרם
2. שלח `/start`
3. אמור לקבל הודעת ברוכים הבאים
4. שלח טקסט כלשהו
5. אמור לקבל אישור שמירה

### 5.3 בדיקת Web App
1. לחץ על כפתור "פתח את הארכיון" בבוט
2. אמור לראות את הממשק
3. חפש את מה ששלחת
4. אמור למצוא תוצאות

## שלב 6: Monitoring

### 6.1 לוגים ב-Render
1. עבור ל-Logs tab
2. בדוק שאין שגיאות
3. חפש שורות:
   - "Database initialized"
   - "Bot initialized"
   - "Webhook set to..."

### 6.2 Telegram Webhook Info
בדוק שה-webhook מוגדר נכון:
```bash
curl https://api.telegram.org/bot<YOUR-TOKEN>/getWebhookInfo
```

אמור להראות:
```json
{
  "ok": true,
  "result": {
    "url": "https://YOUR-APP.onrender.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

## בעיות נפוצות ופתרונות

### הבוט לא עונה
```bash
# אפס את ה-webhook
curl -X POST https://api.telegram.org/bot<TOKEN>/deleteWebhook

# הגדר מחדש (Render יעשה זאת אוטומטית בהפעלה הבאה)
# או הפעל restart מ-Render Dashboard
```

### שגיאות Database
```bash
# בדוק connection string
# ודא ש-pgvector מופעל
# בדוק שאין בעיות חיבור ברשת
```

### 503 Service Unavailable
```bash
# המתן דקה - Render עשוי לעשות cold start
# בדוק logs - אולי יש שגיאה בקוד
# ודא שכל המשתנים מוגדרים
```

### AI לא עובד
```bash
# בדוק שה-API key תקף
# ודא שיש quota ב-Google AI
# בדוק logs לשגיאות ספציפיות
```

## העלאת גרסה חדשה

```bash
# עדכן קוד
git add .
git commit -m "Feature: added X"
git push

# Render יעשה deploy אוטומטית
# עקוב אחרי ה-logs
```

## סקלינג

### להגדיל Workers
Render Dashboard → Settings → Instance:
- Instance Type: שנה ל-Standard (2GB RAM)
- Workers: הוסף בפקודת ה-start: `--workers 4`

### כשצריך Redis
1. צור Redis instance ב-Render
2. העתק את ה-REDIS_URL
3. הוסף למשתני סביבה
4. עדכן את הקוד לשימוש ב-caching

---

**מוכן! 🚀**

הבוט שלך אמור לעבוד עכשיו ב-production.
