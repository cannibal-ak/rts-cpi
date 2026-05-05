"""ORM models — import all so Alembic can detect them."""

from app.models.tenant import Tenant, ApiClient  # noqa: F401
from app.models.user import AppUser, RoleBinding  # noqa: F401
from app.models.tenant_feature import TenantFeature  # noqa: F401
from app.models.source import SourceSystem, SourceConnection, SourceFile  # noqa: F401
from app.models.ingestion import IngestionJob, IngestionAuditLog  # noqa: F401
from app.models.velocity import VelocitySnapshot  # noqa: F401
from app.models.airline import AirlineCpiSnapshot  # noqa: F401
from app.models.cfl import CflCpiSnapshot  # noqa: F401
from app.models.alerts import AlertRule, AlertEvent  # noqa: F401
from app.models.audit import AuditEvent  # noqa: F401
from app.models.admin import ProviderContract, SavedView, ExportJob  # noqa: F401
from app.models.sftp import (  # noqa: F401
    SftpConnection,
    IngestionSchedule,
    IngestionRun,
    IngestedFile,
)
