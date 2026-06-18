from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    app_name: str = "RTS CPI API"
    
    # Database
    database_url: str = os.environ.get("CPI_DATABASE_URL", "postgresql://cpi:cpi_secret@postgres:5432/cpi_db")
    database_url_rls: str = os.environ.get("CPI_DATABASE_URL_RLS", "postgresql://cpi_app:cpi_app_secret@postgres:5432/cpi_db")
    
    # Infrastructure
    rabbitmq_url: str = os.environ.get("CPI_RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    redis_url: str = os.environ.get("CPI_REDIS_URL", "redis://redis:6379/0")
    
    # Tenant
    default_tenant_id: str = os.environ.get("CPI_DEFAULT_TENANT_ID", "a0000000-0000-0000-0000-000000000001")
    
    # Superset
    superset_url: str = os.environ.get("SUPERSET_URL", "http://superset:8088")
    superset_admin_user: str = os.environ.get("SUPERSET_ADMIN_USER", "admin")
    superset_admin_pass: str = os.environ.get("SUPERSET_ADMIN_PASS", "admin")
    
    # Authentication — JWT + Bcrypt (Phase 2)
    jwt_secret_key: str = os.environ.get("JWT_SECRET_KEY", "CHANGE-ME-IN-PRODUCTION")
    jwt_algorithm: str = os.environ.get("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes: int = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    jwt_refresh_token_expire_days: int = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    password_min_length: int = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))
    bcrypt_rounds: int = int(os.environ.get("BCRYPT_ROUNDS", "12"))

    # Fernet key for SFTP connection password encryption (pre-existing,
    # used by app.core.crypto for sftp_connections.password_ciphertext).
    cpi_kek: str = os.environ.get("CPI_KEK", "")

    # Separate Fernet key for SMTP credential encryption (smtp_config password).
    # MUST be a valid Fernet key (base64-urlsafe, 32 bytes). Generate once with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing this value forfeits the ability to decrypt anything stored under it.
    smtp_encryption_key: str = os.environ.get("CPI_SMTP_ENCRYPTION_KEY", "")

    # System user email for automated tasks (SFTP pulls, etc.) — must exist in app_user.
    system_user_email: str = os.environ.get("CPI_SYSTEM_USER_EMAIL", "admin@rts.com")

    # Platform tenant slug (the internal RTS tenant, excluded from customer-tenant lists).
    platform_tenant_slug: str = os.environ.get("CPI_PLATFORM_TENANT_SLUG", "rts")

    # Public base URL of the web app — used to build links emailed to users
    # (e.g. the accept-invite link). Prod overrides via env APP_BASE_URL.
    APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "http://192.168.101.10:9090")

    # Feature flags
    allow_legacy_header_auth: bool = os.environ.get("ALLOW_LEGACY_HEADER_AUTH", "false").lower() == "true"

    # MFA enforcement (Phase 2C). When True, non-exempt, non-platform-admin
    # users must enroll in TOTP MFA and complete the second step at login.
    # Default OFF — the two-step /login branch and the forced-enrollment gate
    # are inert (unreachable) until this is flipped to true.
    mfa_enforced: bool = os.environ.get("MFA_ENFORCED", "false").lower() == "true"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://192.168.101.10:8080",
        "http://192.168.101.10:9090",
        "http://192.168.101.10:5173",
    ]

    class Config:
        case_sensitive = False

settings = Settings()
