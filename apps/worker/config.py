from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    server_url: str = "http://localhost:3001/api"
    worker_port: int = 8000
    worker_secret: str = "telecode-worker-secret-change-in-prod"
    github_token: str = ""


settings = Settings()
