/**
 * Admin Settings → Email
 *
 * One-screen form for the platform-wide SMTP credentials that back
 * the forgot-password flow. The encrypted password is never returned
 * by the server; password_set on the read response tells us whether
 * one is currently stored. Leaving the password field blank on an
 * existing config sends the PUT without a password, so the server
 * keeps its existing encrypted value.
 *
 * Test Connection:
 *   - If the admin has typed a password, /test is called with
 *     config_override = the current form values (test BEFORE saving).
 *   - If the password field is empty AND a saved config exists,
 *     /test is called with no override (test the saved row).
 *   - Otherwise the button is disabled and a tooltip explains why.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  Alert, AlertTitle, Box, Button, CircularProgress, Container, Divider,
  FormControl, FormControlLabel, FormHelperText, FormLabel, IconButton,
  InputAdornment, Paper, Radio, RadioGroup, Snackbar, Stack, TextField,
  Tooltip, Typography,
} from '@mui/material';
import {
  CheckCircle, ErrorOutline, MailOutline, Visibility,
  VisibilityOff,
} from '@mui/icons-material';
import PageHeader from '../../../components/common/PageHeader';
import { api } from '../../../api';
import type { ApiErrorShape } from '../../../api/httpClient';
import type {
  SmtpConfigRead, SmtpEncryption, SmtpConfigUpdate, SmtpConfigCreate,
} from '../../../types/smtpConfig';

interface FormState {
  host: string;
  port: string;          // string in form state so the input can be cleared
  encryption: SmtpEncryption;
  username: string;
  password: string;      // blank means "keep existing" on edit
  fromEmail: string;
  fromName: string;
  testRecipient: string;
}

const EMPTY_FORM: FormState = {
  host: '',
  port: '587',
  encryption: 'STARTTLS',
  username: '',
  password: '',
  fromEmail: 'noreply@rtscorp.com',
  fromName: 'RTS CPI Platform',
  testRecipient: '',
};

interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function isValidEmail(value: string): boolean {
  // Cheap front-end check. The server applies the real validation.
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function EmailSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SmtpConfigRead | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [snackbar, setSnackbar] = useState<SnackbarState>({
    open: false, message: '', severity: 'info',
  });

  const showToast = (
    message: string, severity: SnackbarState['severity'] = 'info',
  ) => {
    setSnackbar({ open: true, message, severity });
  };

  const closeToast = () => setSnackbar(s => ({ ...s, open: false }));

  // ── Load on mount ─────────────────────────────

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    api.admin.settings.smtp.get()
      .then(row => {
        if (cancelled) return;
        if (row) {
          setSaved(row);
          setForm({
            host: row.host,
            port: String(row.port),
            encryption: row.encryption,
            username: row.username,
            password: '',
            fromEmail: row.from_email,
            fromName: row.from_name,
            testRecipient: '',
          });
        } else {
          setSaved(null);
          setForm(EMPTY_FORM);
        }
      })
      .catch((err: Error & ApiErrorShape) => {
        if (cancelled) return;
        setLoadError(err.message || 'Failed to load SMTP settings.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // ── Derived state ─────────────────────────────

  const portNumber = useMemo(() => {
    const n = Number(form.port);
    return Number.isFinite(n) ? Math.trunc(n) : NaN;
  }, [form.port]);

  const formErrors: Partial<Record<keyof FormState, string>> = useMemo(() => {
    const e: Partial<Record<keyof FormState, string>> = {};
    if (!form.host.trim()) e.host = 'Required';
    if (!Number.isFinite(portNumber) || portNumber < 1 || portNumber > 65535) {
      e.port = 'Port must be 1–65535';
    }
    if (!form.username.trim()) e.username = 'Required';
    if (!form.fromEmail.trim() || !isValidEmail(form.fromEmail)) {
      e.fromEmail = 'Enter a valid email';
    }
    if (!form.fromName.trim()) e.fromName = 'Required';
    if (!saved && !form.password) {
      e.password = 'Password is required when no SMTP config exists yet';
    }
    return e;
  }, [form, portNumber, saved]);

  const hasErrors = Object.keys(formErrors).length > 0;

  // Test button gating:
  //   - admin typed a password → test with config_override
  //   - password blank + saved config exists → test saved row
  //   - password blank + no saved config → disabled
  const canTestWithOverride = form.password.length > 0;
  const canTestSaved = !form.password && !!saved;
  const canTest =
    isValidEmail(form.testRecipient)
    && !hasErrors
    && (canTestWithOverride || canTestSaved);
  const testDisabledReason =
    !isValidEmail(form.testRecipient)
      ? 'Enter a valid recipient email above.'
      : hasErrors
        ? 'Fix the highlighted form errors first.'
        : (!canTestWithOverride && !canTestSaved)
          ? 'Type the SMTP password to test, or save a config first.'
          : '';

  // ── Status banner ─────────────────────────────

  const banner: { severity: 'success' | 'error' | 'warning' | 'info'; title: string; body: string } =
    !saved
      ? {
        severity: 'warning',
        title: 'Not configured',
        body:
          'Forgot-password emails are not being delivered. Until SMTP is '
          + 'configured, admins must share reset codes manually from the '
          + 'Password Management page.',
      }
      : saved.last_test_status === 'failed'
        ? {
          severity: 'error',
          title: 'Last test failed',
          body:
            (saved.last_test_error || 'See server logs for details.')
            + (saved.last_test_at ? `  (tested ${formatTimestamp(saved.last_test_at)})` : ''),
        }
        : saved.last_test_status === 'success'
          ? {
            severity: 'success',
            title: 'Connected',
            body: saved.last_test_at
              ? `Last successful test ${formatTimestamp(saved.last_test_at)}.`
              : 'SMTP credentials are stored. Run a test to verify delivery.',
          }
          : {
            severity: 'info',
            title: 'Configured (not yet tested)',
            body: 'SMTP credentials are stored. Click Send test to verify delivery.',
          };

  // ── Save ──────────────────────────────────────

  const handleSave = async () => {
    if (hasErrors) {
      showToast('Fix the highlighted form errors first.', 'error');
      return;
    }
    setSaving(true);
    try {
      const body: SmtpConfigUpdate = {
        host: form.host.trim(),
        port: portNumber,
        encryption: form.encryption,
        username: form.username.trim(),
        from_email: form.fromEmail.trim(),
        from_name: form.fromName.trim(),
      };
      if (form.password) body.password = form.password;
      const row = await api.admin.settings.smtp.update(body);
      setSaved(row);
      setForm(f => ({ ...f, password: '' }));
      showToast('SMTP settings saved.', 'success');
    } catch (err) {
      const message = (err as Error & ApiErrorShape).message || 'Save failed.';
      showToast(message, 'error');
    } finally {
      setSaving(false);
    }
  };

  // ── Cancel ────────────────────────────────────

  const handleCancel = () => {
    if (saved) {
      setForm({
        host: saved.host,
        port: String(saved.port),
        encryption: saved.encryption,
        username: saved.username,
        password: '',
        fromEmail: saved.from_email,
        fromName: saved.from_name,
        testRecipient: form.testRecipient,
      });
    } else {
      setForm({ ...EMPTY_FORM, testRecipient: form.testRecipient });
    }
  };

  // ── Test ──────────────────────────────────────

  const handleTest = async () => {
    if (!canTest) return;
    setTesting(true);
    try {
      const override: SmtpConfigCreate | undefined = canTestWithOverride
        ? {
          host: form.host.trim(),
          port: portNumber,
          encryption: form.encryption,
          username: form.username.trim(),
          password: form.password,
          from_email: form.fromEmail.trim(),
          from_name: form.fromName.trim(),
        }
        : undefined;
      const res = await api.admin.settings.smtp.test({
        to_email: form.testRecipient.trim(),
        config_override: override,
      });
      const detail = res.latency_ms != null ? ` (${res.latency_ms} ms)` : '';
      showToast(res.message + detail, res.success ? 'success' : 'error');
      // If we tested the saved config, the server updated last_test_*;
      // re-fetch so the banner reflects the new state.
      if (!override) {
        try {
          const row = await api.admin.settings.smtp.get();
          if (row) setSaved(row);
        } catch {
          // Non-fatal — the test result toast is already shown.
        }
      }
    } catch (err) {
      const message = (err as Error & ApiErrorShape).message || 'Test failed.';
      showToast(message, 'error');
    } finally {
      setTesting(false);
    }
  };

  // ── Render ────────────────────────────────────

  if (loading) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <PageHeader
          title="Email Settings"
          subtitle="Platform-wide SMTP configuration for transactional email."
        />
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (loadError) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <PageHeader
          title="Email Settings"
          subtitle="Platform-wide SMTP configuration for transactional email."
        />
        <Alert severity="error" sx={{ mt: 2 }}>{loadError}</Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <PageHeader
        title="Email Settings"
        subtitle="SMTP credentials used to deliver password-reset emails and other transactional messages."
      />

      <Alert
        severity={banner.severity}
        icon={
          banner.severity === 'success' ? <CheckCircle fontSize="inherit" />
            : banner.severity === 'error' ? <ErrorOutline fontSize="inherit" />
              : <MailOutline fontSize="inherit" />
        }
        sx={{ mb: 3 }}
      >
        <AlertTitle>{banner.title}</AlertTitle>
        {banner.body}
      </Alert>

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>
          SMTP server
        </Typography>

        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              label="Host"
              required
              fullWidth
              size="small"
              value={form.host}
              onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
              error={!!formErrors.host}
              helperText={formErrors.host || 'e.g. smtp.sendgrid.net'}
            />
            <TextField
              label="Port"
              required
              size="small"
              value={form.port}
              onChange={e => setForm(f => ({ ...f, port: e.target.value.replace(/[^\d]/g, '') }))}
              error={!!formErrors.port}
              helperText={formErrors.port || '587 (STARTTLS), 465 (SSL/TLS)'}
              sx={{ width: 130 }}
              inputProps={{ inputMode: 'numeric' }}
            />
          </Stack>

          <FormControl>
            <FormLabel sx={{ fontSize: 13 }}>Encryption</FormLabel>
            <RadioGroup
              row
              value={form.encryption}
              onChange={e => setForm(f => ({ ...f, encryption: e.target.value as SmtpEncryption }))}
            >
              <FormControlLabel value="NONE" control={<Radio size="small" />} label="None" />
              <FormControlLabel value="STARTTLS" control={<Radio size="small" />} label="STARTTLS" />
              <FormControlLabel value="SSL_TLS" control={<Radio size="small" />} label="SSL / TLS" />
            </RadioGroup>
          </FormControl>

          <TextField
            label="Username"
            required
            fullWidth
            size="small"
            value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            error={!!formErrors.username}
            helperText={formErrors.username || 'SMTP login (often the same as From email)'}
          />

          <TextField
            label="Password"
            required={!saved}
            fullWidth
            size="small"
            type={showPassword ? 'text' : 'password'}
            value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            error={!!formErrors.password}
            helperText={
              formErrors.password
              || (saved?.password_set
                ? 'A password is stored. Leave blank to keep it; type a new value to rotate.'
                : 'Stored encrypted at rest; never returned by the API.')
            }
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    size="small"
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    onClick={() => setShowPassword(s => !s)}
                  >
                    {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>
          Sender identity
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
          <TextField
            label="From email"
            required
            fullWidth
            size="small"
            value={form.fromEmail}
            onChange={e => setForm(f => ({ ...f, fromEmail: e.target.value }))}
            error={!!formErrors.fromEmail}
            helperText={formErrors.fromEmail || 'Address shown in the recipient inbox'}
          />
          <TextField
            label="From name"
            required
            fullWidth
            size="small"
            value={form.fromName}
            onChange={e => setForm(f => ({ ...f, fromName: e.target.value }))}
            error={!!formErrors.fromName}
            helperText={formErrors.fromName || 'Display name shown alongside the From address'}
          />
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>
          Test connection
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          Sends a single message to the address below using the current
          form values when a password is entered, or the saved config
          otherwise.
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
          <TextField
            label="Send test message to"
            fullWidth
            size="small"
            value={form.testRecipient}
            onChange={e => setForm(f => ({ ...f, testRecipient: e.target.value }))}
            placeholder="you@yourcompany.com"
          />
          <Tooltip title={testDisabledReason} disableHoverListener={canTest}>
            <span>
              <Button
                variant="outlined"
                onClick={handleTest}
                disabled={!canTest || testing}
                startIcon={testing ? <CircularProgress size={14} /> : <MailOutline />}
                sx={{ whiteSpace: 'nowrap', minWidth: 140 }}
              >
                {testing ? 'Sending…' : 'Send test'}
              </Button>
            </span>
          </Tooltip>
        </Stack>
      </Paper>

      <Divider sx={{ mb: 2 }} />

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'stretch', sm: 'center' }}
        spacing={2}
      >
        <FormHelperText sx={{ m: 0 }}>
          Saves are logged to the platform audit trail. The password is
          encrypted at rest with the platform master key.
        </FormHelperText>
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button variant="text" onClick={handleCancel} disabled={saving}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || hasErrors}
            startIcon={saving ? <CircularProgress size={14} /> : null}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </Button>
        </Stack>
      </Stack>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={5000}
        onClose={closeToast}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity={snackbar.severity} onClose={closeToast} variant="filled">
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
}
