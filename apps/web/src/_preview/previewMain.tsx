/**
 * THROWAWAY dev-only preview bootstrap — never ship this.
 *
 * There is no backend on the laptop, so the real login flow cannot run. This
 * entry seeds a fake refresh token and stubs window.fetch for the handful of
 * endpoints AuthContext and the sidebar touch, then loads the real app. Pick
 * the persona with ?persona=wm|jy|admin (default wm).
 *
 * Serve via /_sidebar_preview.html; delete both files before committing.
 */

const params = new URLSearchParams(window.location.search);
const persona = params.get('persona') ?? 'wm';

const PERSONAS: Record<string, object> = {
  wm: {
    id: 'u-wm', email: 'winair@airline.com', display_name: 'WinAir Preview',
    tenant_id: 't-wm', tenant_slug: 'wm', roles: ['TENANT_ADMIN'], must_change_password: false,
  },
  jy: {
    id: 'u-jy', email: 'jy@airline.com', display_name: 'JY Preview',
    tenant_id: 't-jy', tenant_slug: 'jy', roles: ['TENANT_ADMIN'], must_change_password: false,
  },
  admin: {
    id: 'u-rts', email: 'admin@rtscorp.com', display_name: 'RTS Admin Preview',
    tenant_id: 't-rts', tenant_slug: 'rts', roles: ['TENANT_ADMIN'], must_change_password: false,
  },
};

sessionStorage.setItem('rts_cpi_refresh_token', 'preview-refresh-token');

const b64url = (o: object) =>
  btoa(JSON.stringify(o)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const fakeJwt = `${b64url({ alg: 'none' })}.${b64url({ sub: 'preview', exp: Math.floor(Date.now() / 1000) + 3600 })}.x`;

const json = (body: object, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

window.fetch = async (input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;

  if (url.includes('/api/v1/auth/refresh')) return json({ access_token: fakeJwt });
  if (url.includes('/api/v1/auth/me')) return json(PERSONAS[persona] ?? PERSONAS.wm);

  if (/\/api\/v1\/superset\/dashboards\/[^/]+\/charts/.test(url)) {
    return json({
      dashboard_title: 'Preview dashboard',
      charts: [
        { slice_id: 101, slice_name: 'Fare trend by route', viz_type: 'echarts_timeseries_line', is_kpi: false },
        { slice_id: 102, slice_name: 'Price position distribution', viz_type: 'dist_bar', is_kpi: false },
        { slice_id: 103, slice_name: 'Route summary table', viz_type: 'table', is_kpi: false },
      ],
    });
  }
  if (/\/api\/v1\/superset\/dashboards\/[^/]+\/tabs/.test(url)) {
    return json({
      tabs: [
        { id: 'TAB-price', label: 'Price Analysis' },
        { id: 'TAB-trend', label: 'Price Trends' },
      ],
      tabs_are_navigation: true,
    });
  }

  return json({ detail: 'preview stub: endpoint not mocked' }, 404);
};

import('../main');
