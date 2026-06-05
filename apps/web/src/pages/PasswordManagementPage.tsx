/**
 * Admin Password Management — list users, reset code queue, generate code,
 * force-reset password. RTS platform admin only.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, IconButton, Button, Stack, CircularProgress, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
  TextField, InputAdornment, Checkbox, FormControlLabel,
  Snackbar, Alert,
} from '@mui/material';
import {
  ContentCopy, Visibility, VisibilityOff, VpnKey, LockReset, Refresh, CheckCircle,
} from '@mui/icons-material';
import PageHeader from '../components/common/PageHeader';
import { api } from '../api';
import type { ApiErrorShape } from '../api/httpClient';
import { useSession } from '../context/SessionContext';
import { getTenantDisplayName } from '../utils/tenantConfig';
import type {
  AdminUserListItem, AdminResetTokenItem,
} from '../types';

// Slug for the RTS platform tenant — its row shows orgName only (no " - SLUG"
// suffix) because it doesn't represent an airline/cruise carrier code.
const PLATFORM_TENANT_SLUG = 'rts';

function formatTenantCell(user: AdminUserListItem): string {
  const orgName = getTenantDisplayName(user.tenant_slug, user.tenant_name);
  if (user.tenant_slug === PLATFORM_TENANT_SLUG) return orgName;
  return `${orgName} - ${user.tenant_slug.toUpperCase()}`;
}

// Display-only role-label overrides for the Password Management table.
// These do NOT change the stored role (still TENANT_ADMIN), the API response,
// or any RBAC check — they only relabel the chip text for two specific
// accounts. Keyed on lowercased email; anything not listed falls through to
// the real role value (TENANT_ADMIN).
const ROLE_LABEL_OVERRIDES: Record<string, string> = {
  'admin@rts.com': 'RTS_SuperAdmin',
  'skyair@airline.com': 'Demo_Admin',
};

function displayRole(user: AdminUserListItem): string {
  return ROLE_LABEL_OVERRIDES[user.email.toLowerCase()] ?? (user.role || '—');
}

const REFRESH_INTERVAL_MS = 30_000;

interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}

interface GenerateDialogState {
  open: boolean;
  user: AdminUserListItem | null;
  generating: boolean;
  generatedCode: string | null;
  error: string;
}

interface ForceResetDialogState {
  open: boolean;
  user: AdminUserListItem | null;
  newPassword: string;
  confirmPassword: string;
  forceChange: boolean;
  showPassword: boolean;
  submitting: boolean;
  error: string;
}

// Self-action confirmation: extra speed-bump shown only when the admin is
// about to generate a code for, or reset, their own account. Other rows
// keep the existing flow (button click → main dialog).
interface SelfConfirmState {
  open: boolean;
  action: 'generate' | 'reset' | null;
  user: AdminUserListItem | null;
}

// ── Password strength ────────────────────────────

function passwordScore(p: string): number {
  let score = 0;
  if (p.length >= 8) score++;
  if (/[A-Z]/.test(p)) score++;
  if (/\d/.test(p)) score++;
  if (/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/.test(p)) score++;
  return score;
}

function strengthMeta(score: number, hasInput: boolean) {
  if (!hasInput) return { label: '', color: 'rgba(0,0,0,0.18)' };
  if (score <= 1) return { label: 'Weak',   color: '#E53935' };
  if (score === 2) return { label: 'Fair',   color: '#FB8C00' };
  if (score === 3) return { label: 'Medium', color: '#FFA000' };
  return                  { label: 'Strong', color: '#2E7D32' };
}

// ── Helpers ──────────────────────────────────────

function formatTimestamp(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function relativeTime(iso: string): string {
  try {
    const diffSec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diffSec < 60) return 'just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
  } catch {
    return iso;
  }
}

function userStatusChip(user: AdminUserListItem) {
  if (!user.is_active) return <Chip size="small" label="Inactive" color="default" />;
  if (user.is_locked)  return <Chip size="small" label="Locked" color="error" />;
  return <Chip size="small" label="Active" color="success" />;
}

function tokenStatusChip(status: AdminResetTokenItem['status']) {
  if (status === 'pending') return <Chip size="small" label="Pending" color="warning" />;
  if (status === 'used')    return <Chip size="small" label="Used" color="success" />;
  return                            <Chip size="small" label="Expired" color="default" />;
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fall through */ }
  // Fallback for non-secure contexts.
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}

// ── Main page ────────────────────────────────────

export default function PasswordManagementPage() {
  const { session } = useSession();
  const adminEmail = session.user.email.toLowerCase();

  const [users, setUsers] = useState<AdminUserListItem[]>([]);
  const [tokens, setTokens] = useState<AdminResetTokenItem[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [tokensLoading, setTokensLoading] = useState(true);
  const [usersError, setUsersError] = useState('');
  const [tokensError, setTokensError] = useState('');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [genDialog, setGenDialog] = useState<GenerateDialogState>({
    open: false, user: null, generating: false, generatedCode: null, error: '',
  });
  const [resetDialog, setResetDialog] = useState<ForceResetDialogState>({
    open: false, user: null, newPassword: '', confirmPassword: '',
    forceChange: true, showPassword: false, submitting: false, error: '',
  });
  const [selfConfirm, setSelfConfirm] = useState<SelfConfirmState>({
    open: false, action: null, user: null,
  });
  const [snackbar, setSnackbar] = useState<SnackbarState>({ open: false, message: '', severity: 'info' });

  const showToast = (message: string, severity: SnackbarState['severity'] = 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  // ── Fetchers ────────────────────────────────────

  const fetchUsers = useCallback(async () => {
    setUsersLoading(true);
    setUsersError('');
    try {
      const r = await api.admin.passwordManagement.listUsers();
      setUsers(r.users);
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setUsersError(e.message || 'Failed to load users.');
    } finally {
      setUsersLoading(false);
    }
  }, []);

  const fetchTokens = useCallback(async () => {
    setTokensError('');
    try {
      const r = await api.admin.passwordManagement.listResetCodes(50);
      setTokens(r.tokens);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setTokensError(e.message || 'Failed to load reset codes.');
    } finally {
      setTokensLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchTokens();
  }, [fetchUsers, fetchTokens]);

  // 30s auto-refresh on the reset code queue.
  useEffect(() => {
    const id = window.setInterval(fetchTokens, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [fetchTokens]);

  // ── Self-action confirmation ────────────────────

  const requestGenerateCode = (user: AdminUserListItem) => {
    if (user.email.toLowerCase() === adminEmail) {
      setSelfConfirm({ open: true, action: 'generate', user });
    } else {
      openGenerateDialog(user);
    }
  };

  const requestResetPassword = (user: AdminUserListItem) => {
    if (user.email.toLowerCase() === adminEmail) {
      setSelfConfirm({ open: true, action: 'reset', user });
    } else {
      openResetDialog(user);
    }
  };

  const cancelSelfConfirm = () => {
    setSelfConfirm({ open: false, action: null, user: null });
  };

  const proceedSelfConfirm = () => {
    const { action, user } = selfConfirm;
    setSelfConfirm({ open: false, action: null, user: null });
    if (!user || !action) return;
    if (action === 'generate') openGenerateDialog(user);
    else openResetDialog(user);
  };

  // ── Generate code flow ──────────────────────────

  const openGenerateDialog = (user: AdminUserListItem) => {
    setGenDialog({ open: true, user, generating: false, generatedCode: null, error: '' });
  };
  const closeGenerateDialog = () => {
    setGenDialog({ open: false, user: null, generating: false, generatedCode: null, error: '' });
  };

  const handleGenerate = async () => {
    if (!genDialog.user) return;
    setGenDialog(s => ({ ...s, generating: true, error: '' }));
    try {
      const r = await api.admin.passwordManagement.generateCode(genDialog.user.email);
      setGenDialog(s => ({ ...s, generating: false, generatedCode: r.code }));
      fetchTokens(); // refresh queue immediately
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setGenDialog(s => ({ ...s, generating: false, error: e.message || 'Failed to generate code.' }));
    }
  };

  const handleCopyCode = async (code: string) => {
    const ok = await copyToClipboard(code);
    showToast(ok ? 'Code copied to clipboard' : 'Could not copy — please copy manually', ok ? 'success' : 'warning');
  };

  // ── Force reset flow ────────────────────────────

  const openResetDialog = (user: AdminUserListItem) => {
    setResetDialog({
      open: true, user, newPassword: '', confirmPassword: '',
      forceChange: true, showPassword: false, submitting: false, error: '',
    });
  };
  const closeResetDialog = () => {
    setResetDialog(s => ({ ...s, open: false, error: '' }));
  };

  const resetScore = passwordScore(resetDialog.newPassword);
  const resetMeta = strengthMeta(resetScore, resetDialog.newPassword.length > 0);
  const passwordsMatch =
    resetDialog.newPassword.length > 0 &&
    resetDialog.newPassword === resetDialog.confirmPassword;

  const handleForceReset = async () => {
    if (!resetDialog.user) return;
    if (!passwordsMatch) {
      setResetDialog(s => ({ ...s, error: 'Passwords do not match.' }));
      return;
    }
    if (resetScore < 2) {
      setResetDialog(s => ({ ...s, error: 'Password is too weak. Use at least 8 characters with uppercase, number, and special character.' }));
      return;
    }
    setResetDialog(s => ({ ...s, submitting: true, error: '' }));
    try {
      await api.admin.passwordManagement.forceReset(
        resetDialog.user.email,
        resetDialog.newPassword,
        resetDialog.forceChange,
      );
      closeResetDialog();
      showToast(`Password reset for ${resetDialog.user.email}`, 'success');
      fetchUsers(); // refresh in case lockout state changed
      fetchTokens();
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setResetDialog(s => ({ ...s, submitting: false, error: e.message || 'Failed to reset password.' }));
    }
  };

  // ── Render ──────────────────────────────────────

  return (
    <Box>
      <PageHeader
        title="Password Management"
        subtitle="Manage user passwords and reset codes"
      />

      {/* ── Section 1: User Accounts ── */}
      <Paper sx={{ p: 2.5, mb: 3, border: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Typography variant="h6">User Accounts</Typography>
          <Tooltip title="Refresh">
            <span>
              <IconButton onClick={fetchUsers} disabled={usersLoading} size="small">
                <Refresh fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Box>

        {usersError && (
          <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setUsersError('')}>
            {usersError}
          </Alert>
        )}

        {usersLoading ? (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Email</TableCell>
                  <TableCell>Tenant</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Last Login</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {users.map(user => (
                  <TableRow key={user.id} hover>
                    <TableCell sx={{ fontFamily: 'inherit' }}>{user.email}</TableCell>
                    <TableCell>{formatTenantCell(user)}</TableCell>
                    <TableCell>
                      <Chip size="small" label={displayRole(user)} variant="outlined" />
                    </TableCell>
                    <TableCell>{userStatusChip(user)}</TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {user.last_login ? formatTimestamp(user.last_login) : 'Never'}
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={1} justifyContent="flex-end">
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<VpnKey fontSize="small" />}
                          onClick={() => requestGenerateCode(user)}
                        >
                          Generate Code
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          color="warning"
                          startIcon={<LockReset fontSize="small" />}
                          onClick={() => requestResetPassword(user)}
                        >
                          Reset Password
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
                {users.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ color: 'text.secondary', py: 3 }}>
                      No users found.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      {/* ── Section 2: Recent Reset Codes ── */}
      <Paper sx={{ p: 2.5, border: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
          <Box>
            <Typography variant="h6">Recent Reset Codes</Typography>
            {lastUpdated && (
              <Typography variant="caption" color="text.secondary">
                Last updated: {relativeTime(lastUpdated.toISOString())} · auto-refreshes every 30s
              </Typography>
            )}
          </Box>
          <Tooltip title="Refresh now">
            <span>
              <IconButton onClick={fetchTokens} disabled={tokensLoading} size="small">
                <Refresh fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        </Box>

        {tokensError && (
          <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setTokensError('')}>
            {tokensError}
          </Alert>
        )}

        {tokensLoading ? (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Email</TableCell>
                  <TableCell>Code</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Requested</TableCell>
                  <TableCell>Expires</TableCell>
                  <TableCell align="right">Attempts</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tokens.map(t => (
                  <TableRow key={t.id} hover>
                    <TableCell>{t.email}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography
                          component="span"
                          sx={{
                            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                            fontSize: 14,
                            letterSpacing: '0.1em',
                            fontWeight: 600,
                          }}
                        >
                          {t.code}
                        </Typography>
                        <Tooltip title="Copy code">
                          <IconButton size="small" onClick={() => handleCopyCode(t.code)}>
                            <ContentCopy sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Tooltip>
                      </Box>
                    </TableCell>
                    <TableCell>{tokenStatusChip(t.status)}</TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {formatTimestamp(t.created_at)}
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {formatTimestamp(t.expires_at)}
                    </TableCell>
                    <TableCell align="right">
                      {t.attempts > 0 ? (
                        <Chip size="small" label={t.attempts} color={t.attempts >= 5 ? 'error' : 'warning'} />
                      ) : (
                        <Typography variant="caption" color="text.secondary">0</Typography>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {tokens.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ color: 'text.secondary', py: 3 }}>
                      No password reset requests yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      {/* ── Generate Code Dialog ── */}
      <Dialog open={genDialog.open} onClose={genDialog.generating ? undefined : closeGenerateDialog} maxWidth="xs" fullWidth>
        <DialogTitle>
          Generate Reset Code{genDialog.user ? ` for ${genDialog.user.email}` : ''}
        </DialogTitle>
        <DialogContent>
          {!genDialog.generatedCode ? (
            <>
              <DialogContentText>
                This will generate a 6-digit code valid for 5 minutes. Give this code to the user so they can reset their password.
              </DialogContentText>
              {genDialog.error && (
                <Alert severity="error" sx={{ mt: 2 }}>{genDialog.error}</Alert>
              )}
            </>
          ) : (
            <>
              <DialogContentText sx={{ mb: 2 }}>
                Share this code with <strong>{genDialog.user?.email}</strong>. It expires in 5 minutes.
              </DialogContentText>
              <Box
                sx={{
                  p: 2.5,
                  textAlign: 'center',
                  bgcolor: (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                  borderRadius: 1,
                  border: 1,
                  borderColor: 'divider',
                  mb: 1.5,
                }}
              >
                <Typography
                  sx={{
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                    fontSize: 36,
                    fontWeight: 700,
                    letterSpacing: '0.3em',
                  }}
                >
                  {genDialog.generatedCode}
                </Typography>
              </Box>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<ContentCopy />}
                onClick={() => genDialog.generatedCode && handleCopyCode(genDialog.generatedCode)}
              >
                Copy Code
              </Button>
            </>
          )}
        </DialogContent>
        <DialogActions>
          {!genDialog.generatedCode ? (
            <>
              <Button onClick={closeGenerateDialog} disabled={genDialog.generating}>Cancel</Button>
              <Button
                onClick={handleGenerate}
                variant="contained"
                disabled={genDialog.generating}
                startIcon={genDialog.generating ? <CircularProgress size={16} color="inherit" /> : null}
              >
                {genDialog.generating ? 'Generating...' : 'Generate'}
              </Button>
            </>
          ) : (
            <Button onClick={closeGenerateDialog} variant="contained">Done</Button>
          )}
        </DialogActions>
      </Dialog>

      {/* ── Force Reset Dialog ── */}
      <Dialog
        open={resetDialog.open}
        onClose={resetDialog.submitting ? undefined : closeResetDialog}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          Reset Password{resetDialog.user ? ` for ${resetDialog.user.email}` : ''}
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Set a new password for this user. They will need to use it on their next login.
          </DialogContentText>

          {resetDialog.error && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setResetDialog(s => ({ ...s, error: '' }))}>
              {resetDialog.error}
            </Alert>
          )}

          <TextField
            label="New Password"
            type={resetDialog.showPassword ? 'text' : 'password'}
            fullWidth
            value={resetDialog.newPassword}
            onChange={(e) => setResetDialog(s => ({ ...s, newPassword: e.target.value }))}
            autoComplete="new-password"
            autoFocus
            sx={{ mb: 1 }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    edge="end"
                    size="small"
                    onClick={() => setResetDialog(s => ({ ...s, showPassword: !s.showPassword }))}
                    aria-label="Toggle password visibility"
                  >
                    {resetDialog.showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          {/* Strength meter */}
          <Box sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              {[0, 1, 2, 3].map((i) => (
                <Box
                  key={i}
                  sx={{
                    flex: 1,
                    height: 4,
                    borderRadius: 2,
                    backgroundColor:
                      resetDialog.newPassword.length > 0 && i < resetScore
                        ? resetMeta.color
                        : (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.08)',
                    transition: 'background-color 150ms ease',
                  }}
                />
              ))}
            </Box>
            {resetMeta.label && (
              <Typography sx={{ fontSize: 11, mt: 0.5, color: resetMeta.color, fontWeight: 600, letterSpacing: '0.05em' }}>
                {resetMeta.label}
              </Typography>
            )}
          </Box>

          <TextField
            label="Confirm Password"
            type={resetDialog.showPassword ? 'text' : 'password'}
            fullWidth
            value={resetDialog.confirmPassword}
            onChange={(e) => setResetDialog(s => ({ ...s, confirmPassword: e.target.value }))}
            autoComplete="new-password"
            sx={{ mb: 1 }}
            error={resetDialog.confirmPassword.length > 0 && !passwordsMatch}
            helperText={resetDialog.confirmPassword.length > 0 && !passwordsMatch ? 'Passwords do not match' : ' '}
          />

          <FormControlLabel
            control={
              <Checkbox
                checked={resetDialog.forceChange}
                onChange={(e) => setResetDialog(s => ({ ...s, forceChange: e.target.checked }))}
              />
            }
            label="Require password change on next login"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={closeResetDialog} disabled={resetDialog.submitting}>Cancel</Button>
          <Button
            onClick={handleForceReset}
            variant="contained"
            color="warning"
            disabled={resetDialog.submitting || !passwordsMatch || resetScore < 2}
            startIcon={resetDialog.submitting ? <CircularProgress size={16} color="inherit" /> : <CheckCircle />}
          >
            {resetDialog.submitting ? 'Resetting...' : 'Reset Password'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Self-action confirmation dialog ── */}
      <Dialog
        open={selfConfirm.open}
        onClose={cancelSelfConfirm}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          {selfConfirm.action === 'reset'
            ? 'Reset your own password?'
            : 'Generate a reset code for yourself?'}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {selfConfirm.action === 'reset' ? (
              <>
                You are about to reset the password for your own account
                {selfConfirm.user ? <> (<strong>{selfConfirm.user.email}</strong>)</> : null}.
                Make sure you have access to the new password before continuing — you
                will be required to log in again with the new value.
              </>
            ) : (
              <>
                This will generate a one-time reset code for your own account. Use it
                carefully — only one code can be active at a time.
              </>
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelSelfConfirm}>Cancel</Button>
          <Button
            onClick={proceedSelfConfirm}
            variant="contained"
            color={selfConfirm.action === 'reset' ? 'warning' : 'primary'}
          >
            {selfConfirm.action === 'reset' ? 'Reset My Password' : 'Generate Code'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => setSnackbar(s => ({ ...s, open: false }))}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
