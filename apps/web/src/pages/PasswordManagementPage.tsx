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
  Select, MenuItem, FormControl, InputLabel,
  Snackbar, Alert,
} from '@mui/material';
import {
  ContentCopy, Visibility, VisibilityOff, VpnKey, LockReset, Refresh, CheckCircle,
  PersonAdd, Email as EmailIcon, Block, HowToReg, DeleteOutline,
} from '@mui/icons-material';
import PageHeader from '../components/common/PageHeader';
import { api } from '../api';
import type { ApiErrorShape } from '../api/httpClient';
import { useSession } from '../context/SessionContext';
import { getTenantDisplayName } from '../utils/tenantConfig';
import type {
  AdminUserListItem, AdminResetTokenItem, AdminTenantOption,
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

// Mirrors the backend privilege guard: an account that is itself an RTS
// platform admin (RTS tenant + TENANT_ADMIN) can never be deactivated or
// deleted, so the platform can't be locked out of itself.
function isPlatformAdmin(user: AdminUserListItem): boolean {
  return (
    user.tenant_slug.toLowerCase() === PLATFORM_TENANT_SLUG &&
    user.role === 'TENANT_ADMIN'
  );
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

interface InviteDialogState {
  open: boolean;
  email: string;
  displayName: string;
  tenantId: string;
  role: string;
  submitting: boolean;
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
  action: 'reset' | null;
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
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState('');

  const [tenants, setTenants] = useState<AdminTenantOption[]>([]);
  const [sendingResetEmail, setSendingResetEmail] = useState<string | null>(null);

  const [inviteDialog, setInviteDialog] = useState<InviteDialogState>({
    open: false, email: '', displayName: '', tenantId: '', role: 'TENANT_ADMIN',
    submitting: false, error: '',
  });
  const [resetDialog, setResetDialog] = useState<ForceResetDialogState>({
    open: false, user: null, newPassword: '', confirmPassword: '',
    forceChange: true, showPassword: false, submitting: false, error: '',
  });
  const [selfConfirm, setSelfConfirm] = useState<SelfConfirmState>({
    open: false, action: null, user: null,
  });
  // Deactivate is a destructive-ish toggle, so it gets a confirm dialog;
  // reactivate does not. togglingStatusId disables a row's toggle in flight.
  const [deactivateConfirm, setDeactivateConfirm] =
    useState<{ open: boolean; user: AdminUserListItem | null }>({ open: false, user: null });
  const [deleteConfirm, setDeleteConfirm] =
    useState<{ open: boolean; user: AdminUserListItem | null }>({ open: false, user: null });
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Blocked dialog driven by a 409 reason from delete OR deactivate.
  const [blockedDialog, setBlockedDialog] = useState<{
    open: boolean;
    user: AdminUserListItem | null;
    reason: 'has_history' | 'last_active_admin' | null;
    message: string;
  }>({ open: false, user: null, reason: null, message: '' });
  const [togglingStatusId, setTogglingStatusId] = useState<string | null>(null);
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

  const fetchTenants = useCallback(async () => {
    try {
      const t = await api.admin.passwordManagement.listTenants();
      setTenants(t);
    } catch {
      // Non-fatal: the Invite dialog will show an empty tenant list.
    }
  }, []);

  useEffect(() => {
    fetchUsers();
    fetchTenants();
  }, [fetchUsers, fetchTenants]);

  // ── Self-action confirmation ────────────────────

  const handleSendResetEmail = async (user: AdminUserListItem) => {
    setSendingResetEmail(user.email);
    try {
      const r = await api.admin.passwordManagement.sendResetEmail({ email: user.email });
      showToast(
        r.sent ? `Reset email sent to ${user.email}` : (r.message || 'Could not send reset email.'),
        r.sent ? 'success' : 'warning',
      );
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to send reset email.', 'error');
    } finally {
      setSendingResetEmail(null);
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
    openResetDialog(user);
  };

  // ── Invite user flow ────────────────────────────

  const openInviteDialog = () => {
    setInviteDialog({
      open: true, email: '', displayName: '', tenantId: '', role: 'TENANT_ADMIN',
      submitting: false, error: '',
    });
  };
  const closeInviteDialog = () => {
    setInviteDialog(s => ({ ...s, open: false, error: '' }));
  };

  const handleInvite = async () => {
    const email = inviteDialog.email.trim().toLowerCase();
    const displayName = inviteDialog.displayName.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setInviteDialog(s => ({ ...s, error: 'Please enter a valid email address.' }));
      return;
    }
    if (!displayName) {
      setInviteDialog(s => ({ ...s, error: 'Please enter a display name.' }));
      return;
    }
    if (!inviteDialog.tenantId) {
      setInviteDialog(s => ({ ...s, error: 'Please select a tenant.' }));
      return;
    }
    setInviteDialog(s => ({ ...s, submitting: true, error: '' }));
    try {
      const r = await api.admin.passwordManagement.inviteUser({
        email,
        display_name: displayName,
        tenant_id: inviteDialog.tenantId,
        role: inviteDialog.role,
      });
      closeInviteDialog();
      if (r.invite_sent) {
        showToast(`Invite sent to ${r.email}`, 'success');
      } else {
        showToast(`User created, but the invite email failed to send to ${r.email}. Use \"Send reset email\" to retry.`, 'warning');
      }
      fetchUsers();
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setInviteDialog(s => ({ ...s, submitting: false, error: e.message || 'Failed to invite user.' }));
    }
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
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      setResetDialog(s => ({ ...s, submitting: false, error: e.message || 'Failed to reset password.' }));
    }
  };

  // ── Deactivate / reactivate flow ────────────

  const requestDeactivate = (user: AdminUserListItem) => {
    setDeactivateConfirm({ open: true, user });
  };
  const cancelDeactivateConfirm = () => {
    setDeactivateConfirm({ open: false, user: null });
  };
  const confirmDeactivate = async () => {
    const user = deactivateConfirm.user;
    setDeactivateConfirm({ open: false, user: null });
    if (!user) return;
    setTogglingStatusId(user.id);
    try {
      await api.admin.passwordManagement.deactivateUser(user.id);
      showToast(`${user.email} has been deactivated`, 'success');
      await fetchUsers(); // refresh row status + header tally from the server
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      if (e.status === 409 && e.errorCode === 'last_active_admin') {
        setBlockedDialog({ open: true, user, reason: 'last_active_admin', message: e.message || '' });
      } else {
        showToast(e.message || 'Failed to deactivate user.', 'error');
      }
    } finally {
      setTogglingStatusId(null);
    }
  };

  // ── Delete flow ─────────────────────────────

  const requestDelete = (user: AdminUserListItem) => setDeleteConfirm({ open: true, user });
  const cancelDeleteConfirm = () => setDeleteConfirm({ open: false, user: null });
  const closeBlockedDialog = () =>
    setBlockedDialog({ open: false, user: null, reason: null, message: '' });
  const confirmDelete = async () => {
    const user = deleteConfirm.user;
    setDeleteConfirm({ open: false, user: null });
    if (!user) return;
    setDeletingId(user.id);
    try {
      await api.admin.passwordManagement.deleteUser(user.id);
      showToast(`${user.email} has been deleted`, 'success');
      await fetchUsers(); // refresh rows + header tally from the server
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      if (e.status === 409 && (e.errorCode === 'has_history' || e.errorCode === 'last_active_admin')) {
        setBlockedDialog({
          open: true,
          user,
          reason: e.errorCode as 'has_history' | 'last_active_admin',
          message: e.message || '',
        });
      } else {
        showToast(e.message || 'Failed to delete user.', 'error');
      }
    } finally {
      setDeletingId(null);
    }
  };
  const handleReactivate = async (user: AdminUserListItem) => {
    setTogglingStatusId(user.id);
    try {
      await api.admin.passwordManagement.reactivateUser(user.id);
      showToast(`${user.email} has been reactivated`, 'success');
      await fetchUsers(); // refresh row status + header tally from the server
    } catch (err: unknown) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to reactivate user.', 'error');
    } finally {
      setTogglingStatusId(null);
    }
  };

  // Active/inactive tally for the card header, derived from the live list.
  const activeCount = users.filter(u => u.is_active).length;
  const inactiveCount = users.length - activeCount;

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
          <Stack direction="row" spacing={1.5} alignItems="baseline">
            <Typography variant="h6">User Accounts</Typography>
            {!usersLoading && users.length > 0 && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {activeCount} active · {inactiveCount} inactive
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <Button size="small" variant="contained" startIcon={<PersonAdd fontSize="small" />} onClick={openInviteDialog}>
              Invite user
            </Button>
            <Tooltip title="Refresh">
              <span>
                <IconButton onClick={fetchUsers} disabled={usersLoading} size="small">
                  <Refresh fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
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
                          startIcon={<EmailIcon fontSize="small" />}
                          onClick={() => handleSendResetEmail(user)}
                          disabled={sendingResetEmail === user.email}
                        >
                          {sendingResetEmail === user.email ? 'Sending…' : 'Send reset email'}
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
                        {user.is_active ? (() => {
                          const isOwn = user.email.toLowerCase() === adminEmail;
                          const isAdmin = isPlatformAdmin(user);
                          const blocked = isOwn || isAdmin;
                          const reason = isOwn
                            ? 'You cannot deactivate your own account.'
                            : 'Protected RTS platform admin accounts cannot be deactivated.';
                          const btn = (
                            <Button
                              size="small"
                              variant="outlined"
                              color="error"
                              startIcon={<Block fontSize="small" />}
                              onClick={() => requestDeactivate(user)}
                              disabled={blocked || togglingStatusId === user.id}
                            >
                              {togglingStatusId === user.id ? 'Working…' : 'Deactivate'}
                            </Button>
                          );
                          return blocked
                            ? <Tooltip title={reason}><span>{btn}</span></Tooltip>
                            : btn;
                        })() : (
                          <Button
                            size="small"
                            variant="outlined"
                            color="success"
                            startIcon={<HowToReg fontSize="small" />}
                            onClick={() => handleReactivate(user)}
                            disabled={togglingStatusId === user.id}
                          >
                            {togglingStatusId === user.id ? 'Working…' : 'Reactivate'}
                          </Button>
                        )}
                        {(() => {
                          const isOwn = user.email.toLowerCase() === adminEmail;
                          const isAdmin = isPlatformAdmin(user);
                          const blocked = isOwn || isAdmin;
                          const reason = isOwn
                            ? 'You cannot delete your own account.'
                            : isAdmin
                              ? 'Protected RTS platform admin accounts cannot be deleted.'
                              : 'Permanently delete this user';
                          return (
                            <Tooltip title={reason}>
                              <span>
                                <IconButton
                                  size="small"
                                  color="error"
                                  aria-label="Delete user"
                                  onClick={() => requestDelete(user)}
                                  disabled={blocked || deletingId === user.id}
                                >
                                  <DeleteOutline fontSize="small" />
                                </IconButton>
                              </span>
                            </Tooltip>
                          );
                        })()}
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

      {/* ── Invite User Dialog ── */}
      <Dialog open={inviteDialog.open} onClose={inviteDialog.submitting ? undefined : closeInviteDialog} maxWidth="xs" fullWidth>
        <DialogTitle>Invite a new user</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            The user will receive an email with a secure link to set their own password. No password is sent by email.
          </DialogContentText>
          {inviteDialog.error && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setInviteDialog(s => ({ ...s, error: '' }))}>
              {inviteDialog.error}
            </Alert>
          )}
          <TextField label="Email" type="email" fullWidth autoFocus value={inviteDialog.email}
            onChange={(e) => setInviteDialog(s => ({ ...s, email: e.target.value }))} autoComplete="off" sx={{ mb: 2 }} />
          <TextField label="Display name" fullWidth value={inviteDialog.displayName}
            onChange={(e) => setInviteDialog(s => ({ ...s, displayName: e.target.value }))} autoComplete="off" sx={{ mb: 2 }} />
          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel id="invite-tenant-label">Tenant</InputLabel>
            <Select labelId="invite-tenant-label" label="Tenant" value={inviteDialog.tenantId}
              onChange={(e) => setInviteDialog(s => ({ ...s, tenantId: e.target.value as string }))}>
              {tenants.map(t => (
                <MenuItem key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.slug.toUpperCase()})</MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel id="invite-role-label">Role</InputLabel>
            <Select labelId="invite-role-label" label="Role" value={inviteDialog.role}
              onChange={(e) => setInviteDialog(s => ({ ...s, role: e.target.value as string }))}>
              <MenuItem value="TENANT_ADMIN">TENANT_ADMIN</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeInviteDialog} disabled={inviteDialog.submitting}>Cancel</Button>
          <Button onClick={handleInvite} variant="contained" disabled={inviteDialog.submitting}
            startIcon={inviteDialog.submitting ? <CircularProgress size={16} color="inherit" /> : <PersonAdd />}>
            {inviteDialog.submitting ? 'Sending…' : 'Send invite'}
          </Button>
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

      {/* ── Deactivate confirmation dialog ── */}
      <Dialog open={deactivateConfirm.open} onClose={cancelDeactivateConfirm} maxWidth="xs" fullWidth>
        <DialogTitle>Deactivate user?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This immediately blocks{' '}
            <strong>{deactivateConfirm.user?.email}</strong>{' '}
            from logging in; they can be reactivated later. Existing password-reset
            actions remain available for this account.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelDeactivateConfirm}>Cancel</Button>
          <Button onClick={confirmDeactivate} variant="contained" color="error" startIcon={<Block />}>
            Deactivate
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Delete confirmation dialog (irreversible) ── */}
      <Dialog open={deleteConfirm.open} onClose={cancelDeleteConfirm} maxWidth="xs" fullWidth>
        <DialogTitle>Permanently delete user?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Permanently delete <strong>{deleteConfirm.user?.email}</strong>? This
            removes their login, MFA and reset data and{' '}
            <strong>cannot be undone</strong>.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={cancelDeleteConfirm}>Cancel</Button>
          <Button onClick={confirmDelete} variant="contained" color="error" startIcon={<DeleteOutline />}>
            Delete permanently
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Blocked dialog: 409 has_history / last_active_admin ── */}
      <Dialog open={blockedDialog.open} onClose={closeBlockedDialog} maxWidth="xs" fullWidth>
        <DialogTitle>
          {blockedDialog.reason === 'has_history' ? 'This user has history' : 'Last active admin'}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {blockedDialog.message ||
              (blockedDialog.reason === 'has_history'
                ? 'This user has activity history and cannot be deleted. Deactivate the account instead.'
                : 'This is the only active admin for the tenant; add or reactivate another admin first.')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeBlockedDialog}>Close</Button>
          {blockedDialog.reason === 'has_history' && (
            <Button
              variant="contained"
              color="error"
              startIcon={<Block />}
              onClick={() => {
                const u = blockedDialog.user;
                closeBlockedDialog();
                if (u) requestDeactivate(u);
              }}
            >
              Deactivate instead
            </Button>
          )}
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
