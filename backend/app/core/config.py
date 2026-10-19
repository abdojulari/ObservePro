from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET_KEYS = {"change-me-in-production", "dev-only-change-me", "change-me"}
INSECURE_PASSWORDS = {"change-me-admin", "changeme", "admin", "password"}
INSECURE_COLLECTOR_TOKENS = {"dev-only-collector-token", "change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ObservePro"
    app_version: str = "0.1.0"
    environment: str = "development"
    secret_key: str = "change-me-in-production"
    jwt_ttl_hours: int = 12
    admin_email: str = "admin@localhost"
    admin_password: str = "change-me-admin"
    database_url: str = "sqlite:///./data/observe.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 600
    login_rate_limit_per_minute: int = 20
    max_body_bytes: int = 1_048_576
    max_batch_size: int = 500
    retention_days: int = 14
    idempotency_ttl_hours: int = 24
    log_level: str = "INFO"
    dev_bootstrap: bool = False
    dev_project_slug: str = "default"
    dev_api_key_file: str = ""
    collector_ingest_token: str = ""
    otlp_grpc_enabled: bool = False
    otlp_grpc_port: int = 4319
    worker_interval_seconds: int = 15
    retention_interval_seconds: int = 3600
    latency_sample_cap: int = 20_000
    service_inactive_seconds: int = 300
    webhook_timeout_seconds: float = 5.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def collector_token_active(self) -> bool:
        token = self.collector_ingest_token.strip()
        if not token:
            return False
        if self.environment.lower() == "production" and token in INSECURE_COLLECTOR_TOKENS:
            return False
        return True

    def insecure_defaults(self) -> list[str]:
        issues: list[str] = []
        if self.secret_key in INSECURE_SECRET_KEYS:
            issues.append("SECRET_KEY")
        if self.admin_password in INSECURE_PASSWORDS:
            issues.append("ADMIN_PASSWORD")
        if (
            self.environment.lower() != "production"
            and self.collector_ingest_token in INSECURE_COLLECTOR_TOKENS
        ):
            issues.append("COLLECTOR_INGEST_TOKEN")
        return issues


@lru_cache
def get_settings() -> Settings:
    return Settings()
