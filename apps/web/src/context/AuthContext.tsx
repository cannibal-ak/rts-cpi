import React, { createContext, useContext, useState, useCallback, useMemo, ReactNode, useEffect } from 'react';

/* ─── Types ─── */
interface AuthUser {
    email: string;
    name: string;
    tenantId: string;
    token: string;
}

interface AuthContextType {
    user: AuthUser | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (email: string, password: string) => Promise<{ success: boolean; error?: string }>;
    logout: () => void;
}

/* ─── Demo credentials ─── */
const DEMO_CREDENTIALS: Record<string, { password: string; name: string; tenantId: string }> = {
    'admin@skywave.com': { password: 'admin123', name: 'Alex Rivera', tenantId: 'a0000000-0000-0000-0000-000000000001' },
    'alex.rivera@skywave.com': { password: 'admin123', name: 'Alex Rivera', tenantId: 'a0000000-0000-0000-0000-000000000001' },
    'jy@airline.com': { password: 'airline123', name: 'Airline_JY', tenantId: 'a0000000-0000-0000-0000-000000000001' },
    'pw@airline.com': { password: 'airline123', name: 'Airline_PW', tenantId: 'bb000000-0000-0000-0000-000000000001' },
    'fjl@cruise.com': { password: 'cruise123', name: 'Cruise_FJL', tenantId: 'cc000000-0000-0000-0000-000000000001' },
};

const AUTH_STORAGE_KEY = 'rts_cpi_auth';

/* ─── Helper: fake JWT-like token ─── */
function createDemoToken(email: string, name: string, tenantId: string): string {
    const payload = { email, name, tenantId, iat: Date.now(), exp: Date.now() + 8 * 60 * 60 * 1000 }; // 8h
    return btoa(JSON.stringify(payload));
}

function parseDemoToken(token: string): AuthUser | null {
    try {
        const payload = JSON.parse(atob(token));
        if (payload.exp && payload.exp < Date.now()) return null; // expired
        return { 
            email: payload.email, 
            name: payload.name, 
            tenantId: payload.tenantId || 'a0000000-0000-0000-0000-000000000001', 
            token 
        };
    } catch {
        return null;
    }
}

/* ─── Context ─── */
const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [isLoading, setIsLoading] = useState(true); // true while we check localStorage

    // On mount: restore session from localStorage
    useEffect(() => {
        try {
            const stored = localStorage.getItem(AUTH_STORAGE_KEY);
            if (stored) {
                const restored = parseDemoToken(stored);
                if (restored) {
                    setUser(restored);
                } else {
                    localStorage.removeItem(AUTH_STORAGE_KEY); // expired or corrupt
                }
            }
        } catch {
            // ignore
        }
        setIsLoading(false);
    }, []);

    const login = useCallback(async (email: string, password: string) => {
        // Simulate a small network delay for realism
        await new Promise(r => setTimeout(r, 600));

        const normalizedEmail = email.trim().toLowerCase();
        const cred = DEMO_CREDENTIALS[normalizedEmail];

        if (!cred || cred.password !== password) {
            return { success: false, error: 'Invalid email or password' };
        }

        const token = createDemoToken(normalizedEmail, cred.name, cred.tenantId);
        const authUser: AuthUser = { email: normalizedEmail, name: cred.name, tenantId: cred.tenantId, token };

        localStorage.setItem(AUTH_STORAGE_KEY, token);
        setUser(authUser);
        return { success: true };
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        setUser(null);
    }, []);

    const value = useMemo(() => ({
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
    }), [user, isLoading, login, logout]);

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within AuthProvider');
    return ctx;
}
