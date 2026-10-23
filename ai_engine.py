"""
AI Engine - Wrapper for Google Gemini API
Handles content analysis and embedding generation
"""
from google import genai
from google.genai import types
import io
import json
import logging
import re
import threading
from typing import Dict, List, Optional
from PIL import Image
from config import Config

logger = logging.getLogger(__name__)

# ה-SDK google-generativeai הוצא משימוש ב-30.11.2025 ואינו מתוחזק; google-genai
# הוא המחליף הרשמי. מקור: https://ai.google.dev/gemini-api/docs/libraries
#
# הלקוח נבנה בקריאה הראשונה ולא בזמן import: genai.Client זורק ValueError כשאין
# מפתח, וזה לא אמור להפיל את טעינת המודול. מפתח חסר מדווח ב-Config.validate.
_CLIENT: Optional[genai.Client] = None
_CLIENT_LOCK = threading.Lock()

# ל-SDK אין timeout כברירת מחדל (HttpOptions.timeout=None), והקריאות רצות בתוך
# בקשת ה-webhook. ניתוח + embedding חייבים להסתיים יחד לפני ה-timeout של gunicorn
# (120 שניות), ולכן תקרה של 45 שניות לכל קריאה.
_REQUEST_TIMEOUT_MS = 45_000

_SAFETY_SETTINGS = [
    types.SafetySetting(category=category, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]


def _get_client() -> genai.Client:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = genai.Client(
                api_key=Config.GOOGLE_API_KEY,
                http_options=types.HttpOptions(timeout=_REQUEST_TIMEOUT_MS),
            )
    return _CLIENT


def _generation_config() -> types.GenerateContentConfig:
    # max_output_tokens כולל את טוקני החשיבה, ולכן תקרה נמוכה חותכת את ה-JSON או
    # מחזירה תשובה ריקה. להורדת זמן ועלות מורידים את thinking_level, לא את התקרה.
    # מקור: https://ai.google.dev/gemini-api/docs/thinking
    # temperature / top_p / top_k הוצאו משימוש החל מ-Gemini 3 ולכן אינם נשלחים.
    # מקור: https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.8
    thinking_config = None
    if Config.GEMINI_THINKING_LEVEL:
        thinking_config = types.ThinkingConfig(thinking_level=Config.GEMINI_THINKING_LEVEL)
    return types.GenerateContentConfig(
        # JSON mode: המודל מחזיר JSON בלבד, בלי גדר markdown סביבו.
        response_mime_type='application/json',
        safety_settings=_SAFETY_SETTINGS,
        thinking_config=thinking_config,
        # אין כלים בקריאה הזו. בלי הכיבוי ה-SDK רושם "AFC is enabled" ב-INFO על כל ניתוח.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _image_part(image_data: bytes) -> types.Part:
    # שולחים את הבייטים המקוריים עם ה-MIME שזוהה. מעבר אובייקט PIL ל-SDK היה מקודד
    # מחדש כ-PNG (pil_to_blob), ותמונת JPEG מטלגרם הייתה גדלה פי כמה בדרך.
    image = Image.open(io.BytesIO(image_data))
    mime_type = Image.MIME.get(image.format or '')
    if not mime_type:
        raise ValueError(f"Unsupported image format: {image.format!r}")
    return types.Part.from_bytes(data=image_data, mime_type=mime_type)


def _response_json(response: types.GenerateContentResponse) -> Dict:
    text = response.text
    if not text:
        # תשובה בלי טקסט: חסימה, או חיתוך לפני שנכתב פלט. הסיבה נכנסת לשגיאה כדי
        # שתגיע ללוג ול-ai_error_message ולא תיבלע כ-"NoneType has no strip".
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise ValueError(
            f"Empty model response (finish_reason={finish_reason}, "
            f"prompt_feedback={response.prompt_feedback})"
        )
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError(f"Expected a JSON object, got {type(result).__name__}")
    return result


def _fallback_analysis(content: str, content_type: str, error: Optional[Exception] = None) -> Dict:
    text = (content or "").strip()
    if content_type == "image":
        display_text = text or "תמונה"
        search_text = text or "תמונה"
        tags = ["תמונה"]
    elif content_type == "link":
        display_text = text or "קישור"
        search_text = text or "קישור"
        tags = ["קישור"]
    else:
        display_text = text[:200] + '...' if len(text) > 200 else text
        search_text = text
        tags = []

    metadata = {'category': content_type, 'ai_error': True}
    if tags:
        metadata['tags'] = tags
    if error:
        metadata['ai_error_message'] = str(error)

    return {
        'display_text': display_text,
        'search_text': search_text,
        'metadata': metadata
    }

# System instruction for content analysis
ANALYSIS_INSTRUCTION = """אתה ארכיונאי אישי חכם. תפקידך לנתח תוכן ולספק מידע מובנה.

עבור כל פריט תוכן, החזר JSON תקין עם השדות הבאים:
{
  "display_text": "תיאור קצר וטבעי בעברית (1-2 משפטים) של מה שנשמר",
  "search_text": "מילות מפתח, ישויות, ועובדות חשובות (בעברית ובאנגלית)",
  "metadata": {
    "tags": ["תגיות", "רלוונטיות"],
    "entities": ["שמות", "מקומות", "ארגונים"],
    "sentiment": "חיובי/שלילי/ניטרלי",
    "category": "קטגוריה ראשית (חשבונית/משימה/מאמר/תמונה/רעיון/אחר)",
    "date": "תאריך אם מוזכר (YYYY-MM-DD)",
    "amount": סכום מספרי אם יש,
    "currency": "מטבע אם יש (ILS/USD/EUR)",
    "location": "מיקום אם מוזכר",
    "priority": "נמוך/בינוני/גבוה",
    "action_required": true/false
  }
}

חשוב:
- תמיד החזר JSON תקין בלבד, ללא טקסט נוסף
- השתמש בעברית עבור display_text
- search_text צריך להכיל גם עברית וגם אנגלית למקסימום כיסוי
- metadata צריך להיות מדויק ומבוסס על התוכן בלבד
- אם אין מידע - השתמש ב-null או השמט את השדה"""


class AIEngine:
    """AI Engine for content analysis and embedding generation"""
    
    @staticmethod
    def analyze_content(
        content: str,
        content_type: str = 'text',
        image_data: Optional[bytes] = None
    ) -> Dict:
        """
        Analyze content using Gemini and extract structured data
        
        Args:
            content: Text content to analyze
            content_type: Type of content (text/image/voice/link)
            image_data: Optional image bytes for vision analysis
            
        Returns:
            Dictionary with display_text, search_text, and metadata
        """
        try:
            # Prepare prompt based on content type
            if content_type == 'image' and image_data:
                prompt = f"""{ANALYSIS_INSTRUCTION}

נתח את התמונה הזו וספק מידע מובנה.

טקסט נלווה (אם יש): {content}

החזר JSON לפי המבנה המבוקש."""
                contents = [prompt, _image_part(image_data)]
                
            else:
                prompt = f"""{ANALYSIS_INSTRUCTION}

נתח את התוכן הבא:

סוג: {content_type}
תוכן:
{content}

החזר JSON לפי המבנה המבוקש."""
                contents = prompt
                
            response = _get_client().models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=contents,
                config=_generation_config(),
            )
            result = _response_json(response)
            
            # Validate required fields
            if 'display_text' not in result:
                result['display_text'] = content[:200] + '...' if len(content) > 200 else content
            if 'search_text' not in result:
                result['search_text'] = content
            # ה-handlers ניגשים ל-metadata כמילון (.get, השמת url), ולכן ערך מכל
            # טיפוס אחר שהמודל החזיר מוחלף במילון ריק.
            if not isinstance(result.get('metadata'), dict):
                result['metadata'] = {}
            
            logger.info(f"Successfully analyzed {content_type} content")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            # Fallback to simple analysis
            return {
                'display_text': content[:200] + '...' if len(content) > 200 else content,
                'search_text': content,
                'metadata': {'category': content_type, 'ai_error': True}
            }
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return _fallback_analysis(content, content_type, error=e)
    
    # Model and dimension constants for embeddings
    EMBED_MODEL = Config.EMBEDDING_MODEL
    EMBED_DIM = Config.EMBEDDING_DIMENSION  # 768

    @staticmethod
    def build_document_text(display_text: str, search_text: str, content_type: str) -> str:
        """
        The exact text a memory is embedded from.

        Shared by every writer of Memory.embedding (the bot handlers and
        reembed_memories.py), so a re-embedded vector matches a fresh one.
        """
        # gemini-embedding-2 לא מקבל task_type; את סוג המשימה מבטאים בפורמט הטקסט.
        # בחיפוש א-סימטרי המסמך נכתב "title: ... | text: ...", ובלי כותרת - title: none.
        # מקור: https://ai.google.dev/gemini-api/docs/embeddings
        body = f"""תיאור: {display_text}
מילות חיפוש: {search_text}
סוג תוכן: {content_type}"""
        return f"title: none | text: {body}"

    @staticmethod
    def _embed(text: str) -> List[float]:
        """
        Generate a single embedding vector with EMBED_MODEL.
        
        IMPORTANT: 
        - No fallback to other models (to avoid mixing embedding spaces)
        - Raises exception on failure (don't save garbage to DB)
            
        Raises:
            ValueError: If text is empty or embedding fails
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("embedding: empty text")
        
        try:
            # ב-gemini-embedding-2 וקטור מקוצר (768 מתוך 3072) מנורמל אוטומטית.
            # מקור: https://ai.google.dev/gemini-api/docs/embeddings
            result = _get_client().models.embed_content(
                model=AIEngine.EMBED_MODEL,
                contents=text,
                config=types.EmbedContentConfig(output_dimensionality=AIEngine.EMBED_DIM),
            )
            
            embeddings = result.embeddings or []
            if len(embeddings) != 1:
                raise ValueError(f"Expected 1 embedding, got {len(embeddings)}")
            embedding = embeddings[0].values
            
            if not embedding or len(embedding) != AIEngine.EMBED_DIM:
                raise ValueError(
                    f"Bad embedding length: expected {AIEngine.EMBED_DIM}, "
                    f"got {0 if not embedding else len(embedding)}"
                )
            
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise ValueError(f"Failed to generate embedding: {e}")

    @staticmethod
    def embed_memory(display_text: str, search_text: str, content_type: str) -> Dict:
        """
        Embed a memory and return the Memory columns that describe the vector.

        The vector and the model that produced it always travel together, so
        no writer can store one without the other:
            Memory(..., **AIEngine.embed_memory(...))

        Returns:
            {'embedding': [...], 'embedding_model': EMBED_MODEL}
        """
        text = AIEngine.build_document_text(display_text, search_text, content_type)
        return {
            'embedding': AIEngine._embed(text),
            'embedding_model': AIEngine.EMBED_MODEL,
        }

    @staticmethod
    def generate_query_embedding(query: str) -> List[float]:
        """
        Generate embedding for search query.
        
        Args:
            query: Search query text
            
        Returns:
            List of floats (embedding vector)
        """
        # הצד של השאילתה בפורמט הא-סימטרי שמתאים ל-build_document_text.
        # מקור: https://ai.google.dev/gemini-api/docs/embeddings
        return AIEngine._embed(f"task: search result | query: {query}")
    
    # Regex pattern for detecting code-like content
    CODE_HINTS_PATTERN = re.compile(
        r"(```|def\s+\w+|class\s+\w+|import\s+\w+|from\s+\w+\s+import|"
        r"function\s+\w+|const\s+\w+|let\s+\w+|var\s+\w+|"
        r"pip\s+install|npm\s+install|Traceback|Exception:|Error:|"
        r"SELECT\s+|INSERT\s+|UPDATE\s+|DELETE\s+|"
        r"\{\s*\n|\}\s*\n|=>\s*\{|\(\)\s*\{)",
        re.IGNORECASE | re.MULTILINE
    )

    @staticmethod
    def enrich_meta(meta: Optional[Dict], search_text: str) -> Dict:
        """
        Enrich metadata with code detection flag.
        
        This helps the hybrid search boost code-related memories when
        the query appears to be about code.
        
        Args:
            meta: Existing metadata dictionary (can be None)
            search_text: Text to analyze for code patterns
            
        Returns:
            Enriched metadata dictionary with 'contains_code' flag
        """
        result = dict(meta or {})
        result["contains_code"] = bool(
            AIEngine.CODE_HINTS_PATTERN.search(search_text or "")
        )
        return result


