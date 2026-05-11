from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str = ""
    esp32_url: str = "http://192.168.1.100"
    esp32_timeout: int = 10
    telegram_bot_token: str = ""
    telegram_default_chat_id: str = ""
    waha_url: str = "http://127.0.0.1:3000"
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_default_number: str = ""
    rate_limit_per_minute: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
