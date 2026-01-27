"""
Configuration module for MyMindIL
Handles all environment variables and settings
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration"""
    
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL:
        # Normalize common Postgres URL formats:
        # - Render/Heroku style: postgres://...
        # - SQLAlchemy expects: postgresql+psycopg://... for psycopg (v3)
        if DATABASE_URL.startswith('postgres://'):
            DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

        # If no explicit driver is specified, default to psycopg (v3).
        if DATABASE_URL.startswith('postgresql://'):
            DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

        # If an explicit psycopg2 driver is specified but not installed, prefer psycopg (v3).
        if DATABASE_URL.startswith('postgresql+psycopg2://'):
            DATABASE_URL = DATABASE_URL.replace('postgresql+psycopg2://', 'postgresql+psycopg://', 1)
    
    # Telegram
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    TELEGRAM_WEBHOOK_URL = os.getenv('TELEGRAM_WEBHOOK_URL')  # https://yourdomain.com/webhook
    TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME')  # For login widget fallback
    
    # Google AI
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    
    # AI Models
    GEMINI_TEXT_MODEL = os.getenv('GEMINI_TEXT_MODEL', 'gemini-pro')
    GEMINI_VISION_MODEL = os.getenv('GEMINI_VISION_MODEL', 'gemini-pro-vision')
    # Backward-compatible single model setting (defaults to text model)
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', GEMINI_TEXT_MODEL)
    EMBEDDING_MODEL = 'models/text-embedding-004'
    EMBEDDING_DIMENSION = 768
    
    # Sentry (Optional)
    SENTRY_DSN = os.getenv('SENTRY_DSN')
    
    # Redis (Optional - for rate limiting)
    REDIS_URL = os.getenv('REDIS_URL')
    
    # Application Settings
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
    SUPPORTED_IMAGE_FORMATS = ['jpg', 'jpeg', 'png', 'webp', 'gif']
    SUPPORTED_AUDIO_FORMATS = ['ogg', 'mp3', 'wav']
    
    @classmethod
    def validate(cls):
        """Validate required configuration"""
        required = ['DATABASE_URL', 'TELEGRAM_TOKEN', 'GOOGLE_API_KEY']
        missing = [key for key in required if not getattr(cls, key)]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True


# Initialize Sentry if DSN is provided
if Config.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        
        sentry_sdk.init(
            dsn=Config.SENTRY_DSN,
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1,
            environment=os.getenv('ENVIRONMENT', 'production')
        )
    except Exception as e:
        print(f"Failed to initialize Sentry: {e}")
