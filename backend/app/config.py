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

    #: Gemini reads a shopping request and returns a structured intent. That
    #: is the whole of its authority: it never sees a policy, never picks a
    #: product and never takes part in an authorization decision. Unset, the
    #: agent falls back to the deterministic rules parser and keeps working.
    gemini_api_key: str = ""
    #: Flash-Lite, not Flash. This is a parsing job -- English in, nine JSON
    #: fields out -- and the lite model answered in 1.2s where 3.6-flash took
    #: 4-20s for the same prompt and no better a reading. It also carries a
    #: larger free-tier allowance, which matters when a demo is run
    #: repeatedly. (gemini-2.5-* is retired for new keys and returns 404.)
    gemini_model: str = "gemini-3.5-flash-lite"
    #: Typical response is ~1.5s. The ceiling is generous because the only
    #: cost of waiting is a slower answer, while cutting a good request short
    #: silently demotes it to the rules parser.
    gemini_timeout_seconds: float = 20.0

    #: QuickCommerce: live product and price data for the catalog.
    #:
    #: Used only by the `sync_catalog` command, never from the request path --
    #: authorization must not wait on a third-party network call, and must
    #: stay deterministic. Location matters: quick-commerce catalogues and
    #: prices are per-store, so lat/lon decide what the sync sees.
    quickcommerce_api_key: str = ""
    quickcommerce_lat: float = 12.9021
    quickcommerce_lon: float = 77.6639
    quickcommerce_pincode: str = "560068"
    quickcommerce_timeout_seconds: float = 45.0

    cors_origins: str = "http://localhost:5173"

    #: Shared secret for the human-facing API (approve, reject, pay, policies).
    #: Unset means the operator surface is open, which is only acceptable when
    #: the server is bound to 127.0.0.1 on a demo machine.
    #: Signing key for user/merchant session tokens. Unset means a random
    #: per-process key: safe, but everyone is logged out on restart.
    session_secret: str = ""

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
