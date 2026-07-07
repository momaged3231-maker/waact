import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    APP_VERSION = os.getenv("APP_VERSION", "1.3.0")
    APP_RELEASE = os.getenv("APP_RELEASE", "MVP V1.3")
    PRD_VERSION = os.getenv("PRD_VERSION", "v5")
    APP_MODE = os.getenv("APP_MODE", "isp").lower()

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./waact.db")

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
    CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "knowledge_base")

    WHATSAPP_WEBHOOK_SECRET = os.getenv("WHATSAPP_WEBHOOK_SECRET", "")
    WHATSAPP_CONNECTOR_URL = os.getenv("WHATSAPP_CONNECTOR_URL", "http://localhost:3001")
    WHATSAPP_CONNECTOR_API_KEY = os.getenv("WHATSAPP_CONNECTOR_API_KEY", "")

    APP_NAME = "WAACT - WhatsApp Automation"
    APP_URL = os.getenv("APP_URL", "http://localhost:8000")
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production")
    DEBUG = os.getenv("DEBUG", "true").lower() == "true"
    AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "admin123")
    AUTH_ROLE = os.getenv("AUTH_ROLE", "admin")

    MAX_RESPONSE_TOKENS = int(os.getenv("MAX_RESPONSE_TOKENS", "500"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

    REPORT_HOUR = int(os.getenv("REPORT_HOUR", "8"))
    FOLLOWUP_HOUR = int(os.getenv("FOLLOWUP_HOUR", "10"))


config = Config()
