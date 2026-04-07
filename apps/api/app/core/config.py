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
