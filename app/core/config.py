from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Yumigura"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    mongodb_url: str = "mongodb://mongo:27017"
    mongodb_db_name: str = "yumigura"

    uploads_dir: str = "./data/uploads"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
