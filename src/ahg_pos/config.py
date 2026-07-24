from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_DIR = PROJECT_ROOT / "schema"


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_local_env()


@dataclass(frozen=True)
class Settings:
    app_name: str = "AHG CONSTRUFERRET POS"
    host: str = os.getenv("AHG_HOST", "127.0.0.1")
    port: int = int(os.getenv("AHG_PORT", "8765"))
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'ahg_demo.db').as_posix()}",
    )
    demo_mode: bool = os.getenv("AHG_DEMO_MODE", "1") != "0"
    company_rnc: str = os.getenv("AHG_COMPANY_RNC", "132907401")
    company_name: str = os.getenv("AHG_COMPANY_NAME", "PARTY S FOOD SRL")
    company_address: str = os.getenv(
        "AHG_COMPANY_ADDRESS",
        "Santiago de los Caballeros, República Dominicana",
    )
    fiscal_environment: str = os.getenv("AHG_FISCAL_ENV", "test")
    imecf_base_url: str = os.getenv(
        "IMECF_BASE_URL",
        "https://ecf-platform-backend-50801509587.us-central1.run.app",
    ).rstrip("/")
    imecf_api_key: str = os.getenv("IMECF_API_KEY", "").strip()
    imecf_enabled: bool = os.getenv("IMECF_ENABLED", "0") == "1"
    imecf_timeout_seconds: int = int(os.getenv("IMECF_TIMEOUT_SECONDS", "30"))
    imecf_expected_issuer_name: str = os.getenv("IMECF_EXPECTED_ISSUER_NAME", "PARTY S FOOD SRL").strip()
    imecf_workspace_name: str = os.getenv("IMECF_WORKSPACE_NAME", "UTESA").strip()
    imecf_company_id: str = os.getenv(
        "IMECF_COMPANY_ID",
        "fe31476c-210e-4667-b26e-d97a0e57c8b9",
    ).strip()
    imecf_portal_base_url: str = os.getenv(
        "IMECF_PORTAL_BASE_URL",
        "https://ecf-platform-frontend-50801509587.us-central1.run.app",
    ).rstrip("/")
    auth_secure_cookie: bool = os.getenv("AHG_AUTH_SECURE_COOKIE", "0") == "1"
    credential_secret: str = os.getenv("AHG_CREDENTIAL_SECRET", "").strip()
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    paypal_environment: str = os.getenv("PAYPAL_ENVIRONMENT", "sandbox").strip().lower()
    paypal_currency: str = os.getenv("PAYPAL_CURRENCY", "USD").strip().upper()
    paypal_dop_per_usd: float = float(os.getenv("PAYPAL_DOP_PER_USD", "60.00"))
    paypal_no_charge: bool = os.getenv("PAYPAL_NO_CHARGE", "1") != "0"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def paypal_api_base_url(self) -> str:
        if self.paypal_environment == "live":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    @property
    def imecf_dashboard_url(self) -> str:
        if not self.imecf_company_id:
            return self.imecf_portal_base_url
        return f"{self.imecf_portal_base_url}/c/{self.imecf_company_id}/dashboard"


settings = Settings()
