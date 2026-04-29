import React, { createContext, useContext, useState, useCallback, useMemo, useEffect, useRef, ReactNode } from 'react';
import { setHttpClientAccessToken } from '../api/httpClient';

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const REFRESH_KEY = 'rts_cpi_refresh_token';

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

interface AuthContextType {
    user: AuthUser | null;
    accessToken: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    mustChangePassword: boolean;
    login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
    logout: () => void;
    changePassword: (currentPassword: string, newPassword: string) => Promise<{ success: boolean; error?: string }>;
}

/* ─── Context ─── */
const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [accessToken, setAccessToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
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
            const refreshToken = localStorage.getItem(REFRESH_KEY);
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
                    localStorage.removeItem(REFRESH_KEY);
                }
            } catch {
                // Network error — don't log out yet, retry on next interaction
            }
        }, refreshIn);
    }, []);

    // On mount: try to restore session from refresh token
    useEffect(() => {
        const refreshToken = localStorage.getItem(REFRESH_KEY);
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
                    localStorage.removeItem(REFRESH_KEY);
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
                    localStorage.removeItem(REFRESH_KEY);
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
                localStorage.removeItem(REFRESH_KEY);
            }
            setIsLoading(false);
        })();

        return () => {
            if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
        };
    }, [scheduleRefresh]);

    const login = useCallback(async (email: string, password: string) => {
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

            // Store refresh token in localStorage
            // Phase 2 compromise — Phase 7 will move to httpOnly cookies
            localStorage.setItem(REFRESH_KEY, data.refresh_token);

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

            return { success: true };
        } catch (err: any) {
            return { success: false, error: `Network error: ${err.message}` };
        }
    }, [scheduleRefresh]);

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
        localStorage.removeItem(REFRESH_KEY);
        setUser(null);
        setAccessToken(null);
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

    const value = useMemo(() => ({
        user,
        accessToken,
        isAuthenticated: !!user,
        isLoading,
        mustChangePassword: user?.mustChangePassword ?? false,
        login,
        logout,
        changePassword,
    }), [user, accessToken, isLoading, login, logout, changePassword]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}
