/**
 * Per-tab auth storage. Uses sessionStorage so each browser tab maintains
 * an independent auth session — logging in as User B in tab 2 no longer
 * overwrites tab 1's session.
 *
 * Only the refresh token is persisted; the access token and user profile
 * live in React state / module memory and are already per-tab.
 *
 * Theme and other UI preferences continue to use localStorage so they
 * persist across tabs and survive tab closure.
 */
const REFRESH_KEY = 'rts_cpi_refresh_token';

export const authStorage = {
  getRefreshToken(): string | null {
    try {
      return sessionStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },

  setRefreshToken(token: string): void {
    try {
      sessionStorage.setItem(REFRESH_KEY, token);
    } catch {
      // sessionStorage unavailable (private mode, quota) — silently no-op;
      // user will need to log in again on next page load.
    }
  },

  removeRefreshToken(): void {
    try {
      sessionStorage.removeItem(REFRESH_KEY);
    } catch {
      // ignore
    }
  },

  /**
   * One-time migration: move a refresh token that's still sitting in
   * localStorage (from before the sessionStorage rollout) into
   * sessionStorage so active users don't get bounced to /login on
   * deploy day. Safe to remove after a few weeks once nobody has the
   * old key lingering.
   */
  migrateFromLocalStorage(): void {
    try {
      if (sessionStorage.getItem(REFRESH_KEY)) return;
      const legacy = localStorage.getItem(REFRESH_KEY);
      if (legacy) {
        sessionStorage.setItem(REFRESH_KEY, legacy);
        localStorage.removeItem(REFRESH_KEY);
      }
    } catch {
      // ignore — both storages unavailable
    }
  },
};
