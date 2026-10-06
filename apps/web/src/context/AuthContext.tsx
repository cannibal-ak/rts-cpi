import React, { createContext, useContext, useState, useCallback, useMemo, useEffect, useRef, ReactNode } from 'react';
import { setHttpClientAccessToken } from '../api/httpClient';
import { clearDatasetCache } from '../api/datasetCache';
import { authStorage } from '../utils/authStorage';
import { mfaVerify, MfaApiError } from '../api/mfa';

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// "Still signed in" ping for the admin Login Activity page. Most sessions end
// by closing the tab (no /logout call), so the last heartbeat is what dates it.
const HEARTBEAT_MS = 5 * 60_000;

/* ─── Types ─── */
interface AuthUser {
    id: string;
    email: string;
    display_name: string;
    tenantId: string;
    tenantSlug: string;
    roles: string[];
    mustChangePassword: boolean;
}

interface LoginResult {
    success: boolean;
    error?: string;
    // True when the backend returned a two-step MFA challenge instead of
    // tokens — the UI should render the challenge screen (state is set here).
    mfaRequired?: boolean;
}

interface AuthContextType {
    user: AuthUser | null;
    accessToken: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    mustChangePassword: boolean;
    // MFA two-step login (challenge token held in memory only, never persisted)
    mfaChallengeActive: boolean;
    login: (email: string, password: string) => Promise<LoginResult>;
    verifyMfa: (code: string, isRecovery?: boolean) => Promise<{ success: boolean; error?: string }>;
    cancelMfaChallenge: () => void;
    logout: () => void;
    changePassword: (currentPassword: string, newPassword: string) => Promise<{ success: boolean; error?: string }>;
}

/* ─── Context ─── */
const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    // In-memory only — deliberately NOT in sessionStorage/localStorage.
    const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null);
    const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Parse JWT payload without verification (for expiry tracking)
    const parseJwtPayload = (token: string): Record<string, any> | null => {
        try {
            const parts = token.split('.');
            if (parts.length !== 3) return null;
            return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
        } catch {
            return null;
        }
    };

    // Schedule access token refresh 60s before expiry
    const scheduleRefresh = useCallback((token: string) => {
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);

        const payload = parseJwtPayload(token);
        if (!payload?.exp) return;

        const expiresIn = payload.exp * 1000 - Date.now();
        const refreshIn = Math.max(expiresIn - 60_000, 5_000); // 60s before expiry, min 5s

        refreshTimerRef.current = setTimeout(async () => {
            const refreshToken = authStorage.getRefreshToken();
            if (!refreshToken) return;

            try {
                const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken }),
                });
                if (res.ok) {
                    const data = await res.json();
                    setAccessToken(data.access_token);
                    scheduleRefresh(data.access_token);
                } else {
                    // Refresh failed — force logout
                    setUser(null);
                    setAccessToken(null);
                    authStorage.removeRefreshToken();
                }
            } catch {
                // Network error — don't log out yet, retry on next interaction
            }
        }, refreshIn);
    }, []);

    // Shared completion for the normal-login and post-MFA-verify token paths.
    const completeAuth = useCallback((data: any) => {
        // Store refresh token in sessionStorage (per-tab isolation).
        // Phase 2 compromise — Phase 7 will move to httpOnly cookies.
        authStorage.setRefreshToken(data.refresh_token);
        setAccessToken(data.access_token);
        setUser({
            id: data.user.id,
            email: data.user.email,
            display_name: data.user.display_name,
            tenantId: data.user.tenant_id,
            tenantSlug: data.user.tenant_slug,
            roles: data.user.roles,
            mustChangePassword: data.must_change_password,
        });
        scheduleRefresh(data.access_token);
    }, [scheduleRefresh]);

    // On mount: try to restore session from refresh token
    useEffect(() => {
        // One-time migration: copy any legacy refresh token still in
        // localStorage (from before per-tab isolation) into sessionStorage
        // so active users aren't bounced to /login on deploy day. Safe to
        // remove after a few weeks once nobody has the old key lingering.
        authStorage.migrateFromLocalStorage();

        const refreshToken = authStorage.getRefreshToken();
        if (!refreshToken) {
            setIsLoading(false);
            return;
        }

        (async () => {
            try {
                // Get a new access token
                const refreshRes = await fetch(`${BASE}/api/v1/auth/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken }),
                });

                if (!refreshRes.ok) {
                    authStorage.removeRefreshToken();
                    setIsLoading(false);
                    return;
                }

                const refreshData = await refreshRes.json();
                const newAccessToken = refreshData.access_token;

                // Fetch user profile
                const meRes = await fetch(`${BASE}/api/v1/auth/me`, {
                    headers: { Authorization: `Bearer ${newAccessToken}` },
                });

                if (!meRes.ok) {
                    authStorage.removeRefreshToken();
                    setIsLoading(false);
                    return;
                }

                const meData = await meRes.json();
                setUser({
                    id: meData.id,
                    email: meData.email,
                    display_name: meData.display_name,
                    tenantId: meData.tenant_id,
                    tenantSlug: meData.tenant_slug,
                    roles: meData.roles,
                    mustChangePassword: meData.must_change_password,
                });
                setAccessToken(newAccessToken);
                scheduleRefresh(newAccessToken);
            } catch {
                authStorage.removeRefreshToken();
            }
            setIsLoading(false);
        })();

        return () => {
            if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        };
    }, [scheduleRefresh]);

    const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
        try {
            const res = await fetch(`${BASE}/api/v1/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Login failed' }));
                const detail = typeof err.detail === 'string' ? err.detail : err.detail?.message || 'Login failed';
                return { success: false, error: detail };
            }

            const data = await res.json();

            // Two-step MFA: backend issued a challenge instead of tokens.
            if (data.mfa_required) {
                setMfaChallengeToken(data.mfa_challenge_token);  // in-memory only
                return { success: false, mfaRequired: true };
            }

            completeAuth(data);
            return { success: true };
        } catch (err: any) {
            return { success: false, error: `Network error: ${err.message}` };
        }
    }, [completeAuth]);

    const verifyMfa = useCallback(async (code: string, isRecovery = false) => {
        if (!mfaChallengeToken) return { success: false, error: 'No MFA challenge in progress' };
        try {
            const data = await mfaVerify(mfaChallengeToken, code, isRecovery);
            completeAuth(data);
            setMfaChallengeToken(null);
            return { success: true };
        } catch (err: any) {
            if (err instanceof MfaApiError && err.status === 423) {
                return { success: false, error: 'Account locked due to too many attempts. Try again later.' };
            }
            const msg = err instanceof MfaApiError ? err.message : `Network error: ${err.message}`;
            return { success: false, error: msg || 'Invalid code' };
        }
    }, [mfaChallengeToken, completeAuth]);

    const cancelMfaChallenge = useCallback(() => {
        setMfaChallengeToken(null);
    }, []);

    const logout = useCallback(async () => {
        if (accessToken) {
            try {
                await fetch(`${BASE}/api/v1/auth/logout`, {
                    method: 'POST',
                    headers: { Authorization: `Bearer ${accessToken}` },
                });
            } catch {
                // Ignore logout errors
            }
        }
        if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        authStorage.removeRefreshToken();
        // Logout is SPA navigation, not a reload — the session dataset cache
        // would survive it and outlive the user on a shared machine.
        clearDatasetCache();
        setUser(null);
        setAccessToken(null);
        setMfaChallengeToken(null);
    }, [accessToken]);

    const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
        if (!accessToken) return { success: false, error: 'Not authenticated' };

        try {
            const res = await fetch(`${BASE}/api/v1/auth/change-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${accessToken}`,
                },
                body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: 'Password change failed' }));
                return { success: false, error: typeof err.detail === 'string' ? err.detail : 'Password change failed' };
            }

            // Update local state
            setUser(prev => prev ? { ...prev, mustChangePassword: false } : null);
            return { success: true };
        } catch (err: any) {
            return { success: false, error: `Network error: ${err.message}` };
        }
    }, [accessToken]);

    // Sync access token to httpClient module
    useEffect(() => {
        setHttpClientAccessToken(accessToken);
    }, [accessToken]);

    // Presence heartbeat while signed in. Fire-and-forget: every failure is
    // ignored (an expired token just skips a beat until the next refresh).
    // Keeps running in background tabs — browsers throttle it, not stop it.
    const accessTokenRef = useRef<string | null>(null);
    accessTokenRef.current = accessToken;
    const signedIn = !!user;
    useEffect(() => {
        if (!signedIn) return;
        const id = setInterval(() => {
            const token = accessTokenRef.current;
            if (!token) return;
            fetch(`${BASE}/api/v1/auth/heartbeat`, {
                method: 'POST',
                headers: { Authorization: `Bearer ${token}` },
            }).catch(() => { /* ignore */ });
        }, HEARTBEAT_MS);
        return () => clearInterval(id);
    }, [signedIn]);

    const value = useMemo(() => ({
        user,
        accessToken,
        isAuthenticated: !!user,
        isLoading,
        mustChangePassword: user?.mustChangePassword ?? false,
        mfaChallengeActive: !!mfaChallengeToken,
        login,
        verifyMfa,
        cancelMfaChallenge,
        logout,
        changePassword,
    }), [user, accessToken, isLoading, mfaChallengeToken, login, verifyMfa, cancelMfaChallenge, logout, changePassword]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}
