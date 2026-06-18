/**
 * MFA + MFA-based-password-reset API calls (Phase 4).
 *
 * Standalone helpers (kept out of the CpiApiClient interface so the mock
 * client is unaffected). All paths are RELATIVE and go through the same
 * BASE the rest of the app uses — never bake an absolute API URL.
 *
 * The mfa_challenge_token and reset_token are passed in by the caller and
 * are NEVER persisted (in-memory only).
 */

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  must_change_password: boolean;
  user: {
    id: string;
    email: string;
    display_name: string;
    tenant_id: string;
    tenant_slug: string;
    roles: string[];
    is_active: boolean;
    must_change_password: boolean;
  };
}

export interface MfaStatus {
  enrolled: boolean;
  enabled: boolean;
  exempt: boolean;
  recovery_codes_remaining: number;
}

export interface EnrollStartResponse {
  provisioning_uri: string;
  secret: string;
}

/** Error carrying the HTTP status so callers can map 423 → lockout, etc. */
export class MfaApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'MfaApiError';
  }
}

async function call<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    });
  } catch (e: any) {
    throw new MfaApiError(0, `Network error: ${e?.message || 'request failed'}`);
  }
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : (detail && (detail.message || detail.code)) || 'Request failed';
    throw new MfaApiError(res.status, message);
  }
  return body as T;
}

function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

// ── Two-step login ───────────────────────────────

export function mfaVerify(challengeToken: string, code: string, isRecovery = false): Promise<TokenResponse> {
  // The backend /verify reads the challenge token from the BODY (mfa_token),
  // not the Authorization header — bare fetch via call(), no Bearer header.
  return call<TokenResponse>('/api/v1/auth/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({ mfa_token: challengeToken, code, is_recovery: isRecovery }),
  });
}

// ── Enrollment / management (access token) ───────

export function mfaEnrollStart(accessToken: string): Promise<EnrollStartResponse> {
  return call<EnrollStartResponse>('/api/v1/auth/mfa/enroll/start', {
    method: 'POST',
    headers: bearer(accessToken),
    body: JSON.stringify({}),
  });
}

export function mfaEnrollConfirm(accessToken: string, code: string): Promise<{ recovery_codes: string[] }> {
  return call<{ recovery_codes: string[] }>('/api/v1/auth/mfa/enroll/confirm', {
    method: 'POST',
    headers: bearer(accessToken),
    body: JSON.stringify({ code }),
  });
}

export function mfaStatus(accessToken: string): Promise<MfaStatus> {
  return call<MfaStatus>('/api/v1/auth/mfa/status', {
    method: 'GET',
    headers: bearer(accessToken),
  });
}

export function mfaDisable(accessToken: string, password: string, code: string): Promise<{ detail: string }> {
  return call<{ detail: string }>('/api/v1/auth/mfa/disable', {
    method: 'POST',
    headers: bearer(accessToken),
    body: JSON.stringify({ password, code }),
  });
}

// ── MFA-based password reset (unauthenticated) ───

export function pwdResetMfaInit(email: string): Promise<{ reset_token: string; expires_in: number; message: string }> {
  return call('/api/v1/auth/password-reset/mfa/init', {
    method: 'POST',
    body: JSON.stringify({ email: email.trim().toLowerCase() }),
  });
}

export function pwdResetMfaVerify(
  resetToken: string,
  code: string,
  newPassword: string,
  isRecovery = false,
): Promise<{ success: boolean; message: string }> {
  return call('/api/v1/auth/password-reset/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({
      reset_token: resetToken,
      code,
      new_password: newPassword,
      is_recovery: isRecovery,
    }),
  });
}
