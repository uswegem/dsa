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
    # Absolute ceiling on a token's lifetime regardless of activity - a
    # secondary safety net. The inactivity settings below are what actually
    # governs a normal session's length; this is just a hard backstop.
    access_token_expire_minutes: int = 480

    upload_dir: str = "uploads"

    # --- Session inactivity / auto-logout ---------------------------------
    # This is a banking-adjacent internal tool: sessions auto-expire after a
    # period of inactivity rather than staying live for the full absolute
    # token lifetime above.
    #
    # session_inactivity_minutes is the CLIENT-FACING policy: app.js tracks
    # mouse/keyboard/scroll/API activity, warns the user ~1 minute before
    # this elapses, and logs them out (revoking the session server-side via
    # POST /api/auth/logout) if nothing resets it.
    #
    # session_inactivity_grace_minutes is the SERVER-ENFORCED ceiling,
    # checked on every authenticated request (app/core/deps.py) and kept
    # slightly longer than the client policy on purpose: app.js throttles
    # its "keep the server-side session fresh" pings to once every 60s, so
    # a hard server cutoff at exactly 10 minutes could occasionally 401 a
    # genuinely-active user a few seconds before their own client-side
    # warning even had a chance to fire. The grace period absorbs that; the
    # client-side timer is what drives the actual UX in the normal case.
    # This also means a token used directly against the API (bypassing the
    # frontend's timer entirely - e.g. a stolen token) can't outlive a real
    # user's inactivity by more than this ceiling, regardless of the
    # absolute JWT expiry above.
    session_inactivity_minutes: int = 10
    session_inactivity_grace_minutes: int = 12

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

    # --- DSA statutory deductions/reporting figures ------------------------
    # DSA only - DTL commission is untouched by any of these.
    #
    # WHT (Withholding Tax) IS deducted: Net Salary (the actual payable
    # amount) = Commission Total (gross) - WHT. See
    # app/services/commission.py - computed per CommissionLine so it stays
    # linear with the existing per-line rate math, then summed like every
    # other report figure.
    dsa_wht_rate: float = 0.05

    # SDL/WCF are statutory REPORTING figures only - computed but never
    # subtracted from what the DSA is paid. Basis is Net Salary (post-WHT),
    # adjusted by any commission_adjustments already applied to that DSA on
    # the run being reported (see app/reports/excel.py::_add_dsa_summary_sheet).
    # Per the legacy spreadsheet this replaces; confirm with Finance before
    # ever changing this to an actual deduction.
    dsa_sdl_rate: float = 0.035
    dsa_wcf_rate: float = 0.005


@lru_cache
def get_settings() -> Settings:
    return Settings()
