"""
AI Engine - Wrapper for Google Gemini API
Handles content analysis and embedding generation
"""
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import logging
import re
import threading
from typing import Dict, List, Optional, Iterable
from config import Config

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=Config.GOOGLE_API_KEY)

# Initialize models
_MODEL_LIST = None
_MODEL_LIST_LOCK = threading.Lock()
_MODEL_CACHE = {"text": None, "vision": None}
_MODEL_NAME_CACHE = {"text": None, "vision": None}


def _build_model(model_name: str) -> genai.GenerativeModel:
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            'temperature': 0.3,
            'top_p': 0.95,
            'top_k': 40,
            'max_output_tokens': 2048,
        },
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )


def _normalize_model_name(name: str) -> str:
    if name.startswith('models/'):
        return name
    return f"models/{name}"


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _looks_like_vision(model_name: str) -> bool:
    lower = model_name.lower()
    return "vision" in lower or "multimodal" in lower or "1.5" in lower


def _list_available_models() -> Dict[str, object]:
    global _MODEL_LIST
    if _MODEL_LIST is not None:
        return _MODEL_LIST
    with _MODEL_LIST_LOCK:
        if _MODEL_LIST is not None:
            return _MODEL_LIST
        try:
            models = list(genai.list_models())
            _MODEL_LIST = {model.name: model for model in models}
        except Exception as e:
            logger.warning(f"Failed to list Gemini models: {e}")
            _MODEL_LIST = {}
    return _MODEL_LIST


def _select_model_name(kind: str) -> Optional[str]:
    if kind == "vision":
        candidates = _dedupe([
            getattr(Config, 'GEMINI_VISION_MODEL', None),
            getattr(Config, 'GEMINI_MODEL', None),
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.0-pro-vision-latest",
            "gemini-pro-vision",
        ])
    else:
        candidates = _dedupe([
            getattr(Config, 'GEMINI_TEXT_MODEL', None),
            getattr(Config, 'GEMINI_MODEL', None),
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro",
        ])

    available = _list_available_models()
    if available:
        normalized_candidates = [_normalize_model_name(name) for name in candidates]
        for name in normalized_candidates:
            model = available.get(name)
            if not model:
                continue
            if "generateContent" not in model.supported_generation_methods:
                continue
            if kind == "vision" and not _looks_like_vision(model.name):
                continue
            return model.name

        for model in available.values():
            if "generateContent" not in model.supported_generation_methods:
                continue
            if kind == "vision" and not _looks_like_vision(model.name):
                continue
            return model.name

    return candidates[0] if candidates else None


def _get_model(kind: str) -> Optional[genai.GenerativeModel]:
    cached = _MODEL_CACHE.get(kind)
    if cached is not None:
        return cached
    model_name = _select_model_name(kind)
    if not model_name:
        return None
    _MODEL_NAME_CACHE[kind] = model_name
    model = _build_model(model_name)
    _MODEL_CACHE[kind] = model
    logger.info(f"Using Gemini {kind} model: {model_name}")
    return model


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
                
                # Upload image to Gemini
                import io
                from PIL import Image
                image = Image.open(io.BytesIO(image_data))
                model = _get_model("vision")
                if model is None:
                    logger.warning("No vision-capable Gemini model available")
                    return _fallback_analysis(content, content_type)
                response = model.generate_content([prompt, image])
                
            else:
                prompt = f"""{ANALYSIS_INSTRUCTION}

נתח את התוכן הבא:

סוג: {content_type}
תוכן:
{content}

החזר JSON לפי המבנה המבוקש."""
                
                model = _get_model("text")
                if model is None:
                    logger.warning("No text Gemini model available")
                    return _fallback_analysis(content, content_type)
                response = model.generate_content(prompt)
            
            # Extract JSON from response
            result_text = response.text.strip()
            
            # Clean markdown code blocks if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()
            
            # Parse JSON
            result = json.loads(result_text)
            
            # Validate required fields
            if 'display_text' not in result:
                result['display_text'] = content[:200] + '...' if len(content) > 200 else content
            if 'search_text' not in result:
                result['search_text'] = content
            if 'metadata' not in result:
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
    # NOTE: task_type is NOT supported by text-embedding-004 (only by embedding-001)
    # See: https://ai.google.dev/api/embeddings
    EMBED_MODEL = "models/text-embedding-004"
    EMBED_DIM = Config.EMBEDDING_DIMENSION  # 768

    @staticmethod
    def generate_embedding(text: str) -> List[float]:
        """
        Generate embedding for text using text-embedding-004.
        
        IMPORTANT: 
        - No fallback to other models (to avoid dimension mismatch)
        - No task_type (not supported by text-embedding-004)
        - Enforces output_dimensionality for consistency
        - Raises exception on failure (don't save garbage to DB)
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector)
            
        Raises:
            ValueError: If text is empty or embedding fails
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("generate_embedding: empty text")
        
        try:
            try:
                result = genai.embed_content(
                    model=AIEngine.EMBED_MODEL,
                    content=text,
                    output_dimensionality=AIEngine.EMBED_DIM,  # Enforce consistent dimensions
                )
            except TypeError as e:
                if "output_dimensionality" not in str(e):
                    raise
                logger.warning(
                    "embed_content does not support output_dimensionality; "
                    "retrying without it"
                )
                result = genai.embed_content(
                    model=AIEngine.EMBED_MODEL,
                    content=text,
                )
            
            # Handle different response formats from the API
            embedding = result.get('embedding')
            if isinstance(embedding, dict) and 'values' in embedding:
                embedding = embedding['values']
            
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
    def generate_query_embedding(query: str) -> List[float]:
        """
        Generate embedding for search query.
        
        NOTE: With text-embedding-004, there's no distinction between document
        and query embeddings (task_type is not supported). We use the same
        function for both, and rely on hybrid search for better results.
        
        Args:
            query: Search query text
            
        Returns:
            List of floats (embedding vector)
        """
        return AIEngine.generate_embedding(query)
    
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

    @staticmethod
    def batch_generate_embeddings(texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        try:
            embeddings = []
            # Gemini API supports batch embedding
            for text in texts:
                embedding = AIEngine.generate_embedding(text)
                embeddings.append(embedding)
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise


