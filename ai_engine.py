"""
AI Engine - Wrapper for Google Gemini API
Handles content analysis and embedding generation
"""
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import json
import logging
from typing import Dict, List, Optional, Tuple
from config import Config

logger = logging.getLogger(__name__)

# Configure Gemini
genai.configure(api_key=Config.GOOGLE_API_KEY)

# Initialize models
analysis_model = genai.GenerativeModel(
    model_name=Config.GEMINI_MODEL,
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
                response = analysis_model.generate_content([prompt, image])
                
            else:
                prompt = f"""{ANALYSIS_INSTRUCTION}

נתח את התוכן הבא:

סוג: {content_type}
תוכן:
{content}

החזר JSON לפי המבנה המבוקש."""
                
                response = analysis_model.generate_content(prompt)
            
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
            raise
    
    @staticmethod
    def generate_embedding(text: str) -> List[float]:
        """
        Generate embedding vector for text using Gemini Embedding API
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            result = genai.embed_content(
                model=Config.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document"
            )
            
            embedding = result['embedding']
            
            # Verify dimension
            if len(embedding) != Config.EMBEDDING_DIMENSION:
                logger.warning(
                    f"Unexpected embedding dimension: {len(embedding)} "
                    f"(expected {Config.EMBEDDING_DIMENSION})"
                )
            
            return embedding
            
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    @staticmethod
    def generate_query_embedding(query: str) -> List[float]:
        """
        Generate embedding for search query
        
        Args:
            query: Search query text
            
        Returns:
            List of floats representing the embedding vector
        """
        try:
            result = genai.embed_content(
                model=Config.EMBEDDING_MODEL,
                content=query,
                task_type="retrieval_query"
            )
            
            return result['embedding']
            
        except Exception as e:
            logger.error(f"Query embedding generation failed: {e}")
            raise
    
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


