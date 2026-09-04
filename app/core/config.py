"""
Application configuration.

Commission rates and the top-up "net" basis are defined here, not scattered
through the codebase, specifically so Finance can correct them later without
touching calculation logic. See the top-up "net" basis section below.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://dsa_app:dsa_app@127.0.0.1:5432/dsa"

    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    upload_dir: str = "uploads"

    # --- Commission rates -------------------------------------------------
    # New Loan (NL): commission on GROSS sales (Disbursement Amt).
    dsa_nl_rate: float = 0.07
    dtl_nl_rate: float = 0.01

    # Top-up (RF): commission on NET sales. See NET_TOPUP_BASIS below for
    # what "net" currently means.
    dsa_rf_rate: float = 0.03
    dtl_rf_rate: float = 0.01

    # --- Top-up "net" basis -------------------------------------------------
    # "net" for a top-up (RF) transaction = Appl Amount minus Letshego
    # Topup (both from the Business Manager file) - i.e. the portion of the
    # applied amount not already covered by Letshego's own top-up
    # settlement. Confirmed by the business owner 2026-09; supersedes the
    # earlier best-current-interpretation (Payout To Client).
    #
    # Still named and isolated here, not inlined in the calculation logic,
    # so it can be corrected again in one place if the definition changes.
    # Maps to BusinessTransaction.appl_amount minus
    # BusinessTransaction.letshego_topup - see
    # app/services/commission.py:get_topup_net_base().
    net_topup_minuend_field: str = "appl_amount"
    net_topup_subtrahend_field: str = "letshego_topup"


@lru_cache
def get_settings() -> Settings:
    return Settings()
