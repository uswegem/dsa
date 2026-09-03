"""
Application configuration.

Commission rates and the top-up "net" basis are defined here, not scattered
through the codebase, specifically so Finance can correct them later without
touching calculation logic. See NET_TOPUP_BASIS_FIELD below.
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
    # BEST-CURRENT-INTERPRETATION, not yet signed off by Finance:
    # "net" for a top-up (RF) transaction = Business Manager file's
    # "Payout To Client" column: the new money actually released to the
    # client after their prior loan balance was settled.
    #
    # This is intentionally named and isolated so it can be corrected in one
    # place if Finance defines "net" differently (e.g. Payout To Client minus
    # fees, or Letshego Topup minus some deduction). It maps to the
    # BusinessTransaction.payout_to_client column — see
    # app/services/commission.py:get_topup_net_base().
    net_topup_basis_field: str = "payout_to_client"


@lru_cache
def get_settings() -> Settings:
    return Settings()
