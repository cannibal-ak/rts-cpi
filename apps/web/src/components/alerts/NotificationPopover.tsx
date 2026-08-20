/**
 * The bell's dropdown: the five most recent alerts, already in context.
 *
 * The "Alert settings" footer link is rendered only for a tenant admin — a
 * TENANT_USER following it would land on /not-authorized, and a dead link in a
 * popover is worse than no link.
 */
import { useNavigate } from 'react-router-dom';
import {
  Box, Button, Divider, Popover, Stack, Typography, useTheme,
} from '@mui/material';
import NotificationsOffOutlined from '@mui/icons-material/NotificationsOffOutlined';

import { useAlerts } from '../../context/AlertsContext';
import { useSession } from '../../context/SessionContext';
import { canEditAlertRules } from '../../alerts/alertsAccess';
import { useTenantChrome } from '../dashboard/tenantChrome';
import { accentColor } from '../../alerts/alertTheme';
import AlertEventRow from './AlertEventRow';

interface Props {
  anchorEl: HTMLElement | null;
  onClose: () => void;
}

export default function NotificationPopover({ anchorEl, onClose }: Props) {
  const navigate = useNavigate();
  const theme = useTheme();
  const chrome = useTenantChrome();
  const { session } = useSession();
  const { recent, unreadCount, error, markRead, markAllRead } = useAlerts();
  const canEdit = canEditAlertRules(session);
  const accent = accentColor(chrome, theme);

  const openEvent = async (id: string) => {
    void markRead([id]).catch(() => { /* surfaced on the page, not here */ });
    onClose();
    navigate(`/alerts?focus=${encodeURIComponent(id)}`);
  };

  return (
    <Popover
      open={Boolean(anchorEl)}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      slotProps={{
        paper: {
          sx: {
            width: 400, mt: 1, borderRadius: 3,
            border: 1, borderColor: 'divider',
            boxShadow: theme.shadows[4],
          },
        },
      }}
    >
      <Stack
        direction="row" alignItems="center" justifyContent="space-between"
        sx={{ px: 2, py: 1.25 }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Notifications
        </Typography>
        <Button
          size="small" disabled={unreadCount === 0}
          onClick={() => { void markAllRead().catch(() => {}); }}
          sx={{ color: accent, textTransform: 'none' }}
        >
          Mark all read
        </Button>
      </Stack>
      <Divider />

      {error ? (
        <Box sx={{ px: 2, py: 3, textAlign: 'center' }}>
          <Typography variant="body2" color="text.secondary">
            Alerts are unavailable right now.
          </Typography>
        </Box>
      ) : recent.length === 0 ? (
        // A compact empty state, not the shared EmptyState component — that one
        // carries py:8 and would blow the popover out to twice its height.
        <Box sx={{ px: 2, py: 4, textAlign: 'center' }}>
          <NotificationsOffOutlined sx={{ fontSize: 28, color: 'text.disabled' }} />
          <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
            No alerts yet
          </Typography>
        </Box>
      ) : (
        <Box sx={{ maxHeight: 420, overflowY: 'auto' }}>
          {recent.map(ev => (
            <AlertEventRow
              key={ev.id} event={ev} variant="compact"
              onClick={() => { void openEvent(ev.id); }}
            />
          ))}
        </Box>
      )}

      <Divider />
      <Stack direction="row" justifyContent="space-between" sx={{ px: 1, py: 0.5 }}>
        <Button
          size="small" sx={{ textTransform: 'none', color: accent }}
          onClick={() => { onClose(); navigate('/alerts'); }}
        >
          View all alerts
        </Button>
        {canEdit && (
          <Button
            size="small" sx={{ textTransform: 'none', color: 'text.secondary' }}
            onClick={() => { onClose(); navigate('/alerts/settings'); }}
          >
            Alert settings
          </Button>
        )}
      </Stack>
    </Popover>
  );
}
