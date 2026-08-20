/**
 * The header bell. Reads context only — it never fetches, so opening the
 * popover costs no request and the badge and the list cannot disagree.
 *
 * Renders null when this session has no alerting, so the AppBar is byte for
 * byte unchanged for the platform admin and for tenants that have not adopted
 * the feature.
 */
import { useState } from 'react';
import type { MouseEvent } from 'react';
import { Badge, IconButton, Tooltip, useTheme } from '@mui/material';
import NotificationsActive from '@mui/icons-material/NotificationsActive';
import NotificationsNoneOutlined from '@mui/icons-material/NotificationsNoneOutlined';

import { useAlerts } from '../../context/AlertsContext';
import { useTenantChrome } from '../dashboard/tenantChrome';
import { badgeColor } from '../../alerts/alertTheme';
import NotificationPopover from './NotificationPopover';

export default function NotificationBell() {
  const { enabled, unreadCount, capped, error } = useAlerts();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const theme = useTheme();
  const chrome = useTenantChrome();

  if (!enabled) return null;

  // A failing poll must never break the header: the bell stays, the badge goes.
  const showBadge = !error && unreadCount > 0;
  const label = error
    ? 'Alerts unavailable'
    : unreadCount > 0
      ? `${unreadCount}${capped ? '+' : ''} unread alert${unreadCount === 1 ? '' : 's'}`
      : 'Alerts';

  return (
    <>
      <Tooltip title={label}>
        <IconButton
          aria-label={label}
          onClick={(e: MouseEvent<HTMLElement>) => setAnchorEl(e.currentTarget)}
          sx={{ color: 'inherit' }}
        >
          <Badge
            badgeContent={showBadge ? unreadCount : 0}
            max={99}
            overlap="circular"
            // aria-live so a screen reader hears the count change without the
            // user having to go looking for it.
            aria-live="polite"
            sx={{
              '& .MuiBadge-badge': {
                bgcolor: badgeColor(chrome, theme),
                color: '#fff', fontWeight: 700, fontSize: 10,
              },
            }}
          >
            {/* The icon changes as well as the badge, so the state is legible
                without relying on colour. */}
            {showBadge ? <NotificationsActive /> : <NotificationsNoneOutlined />}
          </Badge>
        </IconButton>
      </Tooltip>

      <NotificationPopover anchorEl={anchorEl} onClose={() => setAnchorEl(null)} />
    </>
  );
}
