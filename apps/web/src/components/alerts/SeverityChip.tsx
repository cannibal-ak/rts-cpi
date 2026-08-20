/**
 * Severity as icon + word + colour, never colour alone.
 *
 * The outlined variant is not a style preference: the documented warning amber
 * is 1.83:1 on white, so it may colour the border and the icon but never the
 * label. `textSafe` from alertTheme decides which.
 */
import { Chip, useTheme } from '@mui/material';
import ErrorOutlineOutlined from '@mui/icons-material/ErrorOutlineOutlined';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import WarningAmberOutlined from '@mui/icons-material/WarningAmberOutlined';

import { useTenantChrome } from '../dashboard/tenantChrome';
import { severityStyle } from '../../alerts/alertTheme';
import type { AlertSeverity } from '../../types';

const ICONS = {
  info: InfoOutlined,
  warning: WarningAmberOutlined,
  critical: ErrorOutlineOutlined,
} as const;

export default function SeverityChip({ severity }: { severity: AlertSeverity }) {
  const theme = useTheme();
  const chrome = useTenantChrome();
  const style = severityStyle(severity, chrome, theme);
  const Icon = ICONS[style.iconKey];

  return (
    <Chip
      size="small"
      variant="outlined"
      icon={<Icon sx={{ fontSize: 15, color: `${style.color} !important` }} />}
      label={style.label}
      sx={{
        height: 22,
        borderColor: style.color,
        // Only a contrast-safe colour is allowed to be the text.
        color: style.textSafe ? style.color : 'text.primary',
        '& .MuiChip-label': { px: 0.75, fontSize: 11, fontWeight: 600 },
      }}
    />
  );
}
