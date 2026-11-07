from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Config:
    database_url: str = "sqlite:///instance/relay.sqlite3"
    token: str = ""
    webhook_secret: str = ""
    receiver_mode: str = "webhook"
    env: str = "development"
    ai_allowed_models: tuple[str, ...] = ()
    ai_timeout: float = 60
    ai_max_response_bytes: int = 5_000_000
    ai_stream_timeout: float = 240
    ai_stream_idle_timeout: float = 30
    cache_ttl: int = 300
    ai_daily: int = 20
    search_daily: int = 5
    youtube_daily: int = 1
    @classmethod
    def from_env(cls):
        url = os.getenv("DATABASE_URL", cls.database_url)
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        cfg = cls(database_url=url, token=os.getenv("BALE_TOKEN", ""),
                  webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
                  receiver_mode=os.getenv("RECEIVER_MODE", "webhook"),
                  env=os.getenv("APP_ENV", "development"),
                  ai_allowed_models=tuple(x.strip() for x in os.getenv("AI_ALLOWED_MODELS", "").split(",") if x.strip()))
        cfg.validate()
        return cfg
    def validate(self):
        if self.receiver_mode not in {"webhook", "polling"}:
            raise ValueError("Invalid RECEIVER_MODE")
        if self.env == "production":
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires persistent PostgreSQL")
            if not self.token or len(self.webhook_secret) < 32 or self.token == self.webhook_secret:
                raise ValueError("Configure BALE_TOKEN and an independent WEBHOOK_SECRET of at least 32 characters")
    def secret(self, name):
        return os.getenv(name, "")
