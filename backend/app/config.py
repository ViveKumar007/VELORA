from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/velora"

    payment_provider: str = "stub"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    approval_ttl_minutes: int = 15

    cors_origins: str = "http://localhost:5173"

    #: Shared secret for the human-facing API (approve, reject, pay, policies).
    #: Unset means the operator surface is open, which is only acceptable when
    #: the server is bound to 127.0.0.1 on a demo machine.
    operator_token: str = ""

    #: Allow X-User-Id to select an arbitrary user. Local multi-user testing
    #: only -- the header is unauthenticated, so enabling this in any reachable
    #: deployment lets anyone act as anyone.
    dev_allow_user_header: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
