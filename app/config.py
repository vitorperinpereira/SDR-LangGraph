from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "SDR Agent Dental"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_AUDIO_MODEL: str = "gpt-4o-mini-transcribe"
    OPENAI_API_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS: int = 45
    
    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""

    # Redis
    REDIS_URL: str = ""
    REDIS_DEBOUNCE_TTL_SECONDS: int = 30
    
    # Google Calendar
    GCAL_CREDENTIALS_JSON: str = "credentials.json"
    GCAL_CREDENTIALS_B64: str = ""
    GCAL_CALENDAR_ID: str = "primary"
    
    # Google Sheets
    GSHEETS_SPREADSHEET_ID: str = ""
    GSHEETS_RANGE: str = "Leads!A:I"
    
    # Evolution API
    EVOLUTION_API_URL: str = ""
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_WEBHOOK_SECRET: str = ""
    
    # Business Logic
    CLINIC_ID_PILOT: str = ""
    
    # Database Connection String (para LangGraph Checkpointer)
    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
