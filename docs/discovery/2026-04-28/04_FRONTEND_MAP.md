# Frontend Map

## Routes
- `/login`: Public login page.
- `/change-password`: Protected, bypasses the `must_change_password` block.
- `/`: Root router. Admins land on `/` (HomePage), regular users land on `/dashboards`.
- `/cpi/airline/jy`, `/cpi/airline/pw`, `/cpi/cruise/fjl`: Protected, role-gated domain pages.
- `/ingestion`: Job status monitoring for admins.
- `/dashboards` & `/dashboards/:id`: Superset embedded analytics views.
- `/not-authorized`, `*`: Error state pages.

## Auth & Context
- Uses `AuthContext` and `SessionContext` for token storage and user state management.
- `AuthGuard` handles JWT validation, lockout redirects, and forced password changes.
- `ProtectedRoute` enforces role-based and module-based access to specific routes.

## Admin UI
- **Ingestion Trigger**: Available and functional at `/ingestion` (calls `POST /api/v1/ingestion/ingest`).
- **User & Tenant Mgmt**: **MISSING**. No components or routes exist for platform administrators to manage users or tenants.
