/**
 * The two alerts surfaces. Two routes rather than one tabbed route, because
 * they need different roles: a TENANT_USER may read the feed and may not touch
 * the settings. One route with a tab could carry only one guard, which would
 * push the role check into the page body — exactly what ProtectedRoute exists
 * to avoid.
 *
 * With only one tab visible there is nothing to choose between, so the strip
 * renders nothing at all for a non-admin.
 */
import { Tab, Tabs, useTheme } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '../../context/SessionContext';
import { canEditAlertRules } from '../../alerts/alertsAccess';
import { useTenantChrome } from '../../components/dashboard/tenantChrome';
import { accentColor } from '../../alerts/alertTheme';

export default function AlertsTabs() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session } = useSession();
  const theme = useTheme();
  const chrome = useTenantChrome();

  if (!canEditAlertRules(session)) return null;
  const accent = accentColor(chrome, theme);
  const value = pathname.startsWith('/alerts/settings') ? '/alerts/settings' : '/alerts';

  return (
    <Tabs
      value={value}
      onChange={(_, v) => navigate(v)}
      sx={{
        mb: 2, minHeight: 40,
        borderBottom: 1, borderColor: 'divider',
        '& .MuiTab-root': { textTransform: 'none', minHeight: 40, fontWeight: 600 },
        '& .Mui-selected': { color: `${accent} !important` },
        '& .MuiTabs-indicator': { backgroundColor: accent },
      }}
    >
      <Tab label="Alerts" value="/alerts" />
      <Tab label="Alert settings" value="/alerts/settings" />
    </Tabs>
  );
}
