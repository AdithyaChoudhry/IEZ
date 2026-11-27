"""
Configuration settings for the iEZ backend application.
Uses pydantic BaseSettings for environment variable management.
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
import subprocess
from pathlib import Path
from typing import Optional, Union


def _git_version() -> str:
    """V3.<number of commits> (<commit id>) of the running code; 'V3' when there is no git history."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=Path(__file__).resolve().parent, capture_output=True, text=True,
                              timeout=10, check=True).stdout.strip()
    try:
        return f"V3.{git('rev-list', '--count', 'HEAD')} ({git('rev-parse', '--short', 'HEAD')})"
    except (OSError, subprocess.SubprocessError):
        return "V3"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "iEZ API"
    APP_VERSION: str = _git_version()
    DEBUG: bool = True
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Database
    DATABASE_URL: str = "postgresql://iez_user:iez_password@postgres:5432/iez_db"
    
    # CORS
    CORS_ORIGINS: Union[list[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]
    
    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(',')]
        return v
    
    # File upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    TEMP_FILE_DIR: str = "/tmp/iez_uploads"
    # Persistent store for generated deliverables + the source files they came from.
    # Empty = <backend>/document_store
    DOCUMENT_STORE_DIR: str = ""
    FILE_RETENTION_HOURS: int = 1
    # Session-scoped Shared IODB (temporary files; never a project document). Empty dir = <tmp>/iez_shared_iodb.
    SHARED_IODB_DIR: str = ""
    SHARED_IODB_IDLE_MINUTES: int = 480       # unused for this long -> removed
    SHARED_IODB_MAX_BYTES: int = 60 * 1024 * 1024
    
    # AI Extraction
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
