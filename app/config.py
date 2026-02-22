from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "SDR Agent Dental"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5-mini"
    OPENAI_USE_LLM_NODES: bool = True
    OPENAI_AUDIO_MODEL: str = "gpt-4o-mini-transcribe"
    OPENAI_API_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS: int = 45
    PROMPT_PROFILE: str = "v5_1"
    PROMPT_MAX_HISTORY_MESSAGES: int = 15
    PROMPT_ENABLE_ANTI_REPETITION: bool = True
    
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
    
    
    # Evolution API
    EVOLUTION_API_URL: str = ""
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_INSTANCE_ID: str = ""
    EVOLUTION_WEBHOOK_SECRET: str = ""
    EVOLUTION_PRESENCE_DELAY_MS: int = 1200
    
    # Business Logic
    CLINIC_ID_PILOT: str = ""
    
    # Database Connection String (para LangGraph Checkpointer)
    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

settings = Settings()
