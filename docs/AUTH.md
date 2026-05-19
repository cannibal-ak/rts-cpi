# Authentication — RTS CPI (Phase 2)

## Overview

Phase 2 replaces the demo header-based authentication with production-grade
JWT authentication, bcrypt password hashing, forced first-time password change,
and account lockout.

---

## Login Flow

1. User submits `email`, `password`, and `tenant_slug` to `POST /api/v1/auth/login`.
2. Backend resolves the tenant by slug, finds the user within that tenant.
3. Password is verified against bcrypt hash stored in `app_user.password_hash`.
4. On success: returns `access_token` (short-lived) and `refresh_token` (long-lived),
   plus a `must_change_password` flag.
5. Frontend stores the refresh token in `localStorage` (see Security Notes below)
   and holds the access token in React state (memory only).

---

## Token Lifetime

| Token | Lifetime | Storage |
|---|---|---|
| Access token | 30 minutes (configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) | React state (memory) |
| Refresh token | 7 days (configurable via `JWT_REFRESH_TOKEN_EXPIRE_DAYS`) | `localStorage` key: `rts_cpi_refresh_token` |

### Token Payload (Access Token)

```json
{
  "sub": "<user_id UUID>",
  "tenant_id": "<tenant_id UUID>",
  "email": "user@example.com",
  "roles": ["ANALYST", "AIRLINE_USER"],
  "tenant_slug": "jy",
  "token_type": "access",
  "iat": 1712500000,
  "exp": 1712501800,
  "jti": "<unique token id>"
}
```

---

## Refresh Strategy

- The frontend schedules a refresh 60 seconds before access token expiry.
- On 401 from any API call, the HTTP client attempts a single refresh, then retries.
- If refresh fails, the user is logged out and redirected to `/login`.

---

## Account Lockout Policy

- After **5 consecutive failed login attempts**, the account is locked for **15 minutes**.
- The lockout timestamp is stored in `app_user.locked_until`.
- Successful login resets `failed_login_count` to 0 and clears `locked_until`.
- A 423 Locked response is returned for login attempts on locked accounts.

---

## Password Requirements

All passwords must meet:

- Minimum **12 characters** (configurable via `PASSWORD_MIN_LENGTH`)
- At least one **uppercase** letter
- At least one **lowercase** letter
- At least one **digit**
- At least one **special character** (`!@#$%^&*()_+-=[]{}|;:'"<>,.?/~`)

Validation is enforced both client-side (ChangePasswordPage) and server-side
(`validate_password_strength` in `auth_service.py`).

---

## Forced First-Time Password Change

- All seed users have `must_change_password = TRUE`.
- When `must_change_password` is true:
  - Backend returns 403 with `code: "PASSWORD_CHANGE_REQUIRED"` for all non-auth endpoints.
  - Frontend's AuthGuard redirects to `/change-password`.
- Only `POST /api/v1/auth/change-password`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`,
  and `POST /api/v1/auth/refresh` are exempt.
- After successful password change, `must_change_password` is set to `FALSE`.

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | None | Authenticate and receive tokens |
| POST | `/api/v1/auth/refresh` | None (body has refresh_token) | Get new access token |
| POST | `/api/v1/auth/logout` | Bearer | Log out (stub: logs event) |
| POST | `/api/v1/auth/change-password` | Bearer | Change password |
| GET | `/api/v1/auth/me` | Bearer | Get current user profile + roles |

---

## Security Notes (Phase 2 Limitations)

### Refresh Token in localStorage
The refresh token is stored in `localStorage`, which is vulnerable to XSS.
This is a **Phase 2 compromise** documented for remediation in Phase 7.

**Phase 7 plan:** Move to `httpOnly` + `Secure` + `SameSite=Strict` cookies
for refresh tokens, eliminating XSS exposure entirely.

### No Token Revocation List
Currently, logout is a client-side operation (token is discarded). The server
logs the logout event but does not maintain a revocation list. A stolen token
remains valid until expiry.

**Phase 7 plan:** Implement a Redis-backed token revocation list (JTI blacklist)
with TTL matching token expiry.

### No MFA
Multi-factor authentication is not implemented in Phase 2.

**Phase 7 plan:** Add TOTP-based MFA with recovery codes, gated by tenant
feature flag.

---

## Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | (required) | HMAC key for signing JWTs |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `PASSWORD_MIN_LENGTH` | `12` | Minimum password length |
| `BCRYPT_ROUNDS` | `12` | Bcrypt work factor |
| `ALLOW_LEGACY_HEADER_AUTH` | `false` | Enable X-Tenant-ID header fallback |

---

## Seeding Initial Passwords

```bash
docker compose exec api python scripts/seed_auth_passwords.py
```

Migration 016 creates all canonical users with bcrypt-hashed temporary
passwords. The seed script is now an idempotent verification tool that
confirms each user has a `password_hash` set.

---

## Canonical Demo Users

> **Added by migration 016.** The original acme-airways / baltic-ferries
> users from migration 004 were superseded. Migration 016 deletes those
> users, renames tenant acme-airways to skywave, and inserts the canonical
> identity model below.

| Email | Tenant Slug | Display Name | Role | Temp Password |
|---|---|---|---|---|
| `admin@rts.com` | `rts` | RTS Admin | TENANT_ADMIN | `admin123` |
| `jy@airline.com` | `jy` | JY Airline Admin | TENANT_ADMIN | `airline123` |
| `pw@airline.com` | `pw` | PW Airline Admin | TENANT_ADMIN | `airline123` |
| `fjl@cruise.com` | `fjl` | FJL Cruise Admin | TENANT_ADMIN | `cruise123` |

### Tenant Mapping

| Tenant UUID | Slug | Display Name |
|---|---|---|
| `a0000000-0000-0000-0000-000000000001` | `rts` | Revenue Technology Services |
| `dd000000-0000-0000-0000-000000000001` | `jy` | Skywave - JY |
| `bb000000-0000-0000-0000-000000000001` | `pw` | Skybound - PW |
| `cc000000-0000-0000-0000-000000000001` | `fjl` | Baltic Ferries - FJL |

### Important Notes

- **All temporary passwords are forced-change on first login.**
  `must_change_password = TRUE` means the user cannot access any endpoint
  (except auth paths) until they set a new password meeting the 12+ character
  complexity requirements.
- Each user is scoped to their own tenant via RLS. There is no cross-tenant
  access — each TENANT_ADMIN manages only their own tenant's data and settings.
- The temporary passwords (`admin123`, `airline123`, `cruise123`) are weak by
  design — they exist solely to bootstrap the first login. The forced change
  flow ensures they are replaced immediately.
