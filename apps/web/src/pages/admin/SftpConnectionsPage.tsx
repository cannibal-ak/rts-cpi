/**
 * SFTP Connections admin page (Phase 4.2).
 *
 * Lists, creates, edits, deletes, and live-tests SFTP connection
 * records that back scheduled ingestion pulls. RTS platform
 * admins only — gated at the route level via ProtectedRoute and
 * inside the component via ``isSuperAdmin(session)`` for the
 * direct-URL fall-through.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TablePagination, Chip, IconButton, Button, Stack,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
  TextField, RadioGroup, Radio, FormControlLabel, FormLabel, Switch,
  Snackbar, Alert,
} from '@mui/material';
import {
  Add, Edit, PlayArrow, DeleteOutline, Refresh,
} from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';
import { useSession } from '../../context/SessionContext';
import { isSuperAdmin } from '../../utils/access';
import type {
  SftpConnection,
  SftpConnectionCreate,
  SftpConnectionUpdate,
  SftpAuthMethod,
  PageInfo,
} from '../../types';


interface ToastState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}


const DEFAULT_PAGE_SIZE = 20;


// ─── Create / Edit dialog ───────────────────────────────────

interface FormState {
  tenant_code: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: SftpAuthMethod;
  password: string;
  private_key_pem: string;
  remote_base_path: string;
  is_active: boolean;
}

const emptyForm = (): FormState => ({
  tenant_code: '',
  name: '',
  host: '',
  port: 22,
  username: '',
  auth_method: 'password',
  password: '',
  private_key_pem: '',
  remote_base_path: '/upload',
  is_active: true,
});

const initialFromConnection = (conn: SftpConnection): FormState => ({
  tenant_code: conn.tenant_code,
  name: conn.name,
  host: conn.host,
  port: conn.port,
  username: conn.username,
  auth_method: conn.auth_method,
  password: '',
  private_key_pem: '',
  remote_base_path: conn.remote_base_path,
  is_active: conn.is_active,
});


interface ConnectionDialogProps {
  open: boolean;
  mode: 'create' | 'edit';
  initial: SftpConnection | null;
  onClose: () => void;
  onSaved: (saved: SftpConnection, mode: 'create' | 'edit') => void;
  showToast: (message: string, severity: ToastState['severity']) => void;
}

function ConnectionDialog({
  open, mode, initial, onClose, onSaved, showToast,
}: ConnectionDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(mode === 'edit' && initial ? initialFromConnection(initial) : emptyForm());
  }, [open, mode, initial]);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      let saved: SftpConnection;
      if (mode === 'create') {
        const body: SftpConnectionCreate = {
          tenant_code: form.tenant_code.trim(),
          name: form.name.trim(),
          host: form.host.trim(),
          port: form.port,
          username: form.username.trim(),
          auth_method: form.auth_method,
          password: form.auth_method === 'password' ? form.password : undefined,
          private_key_pem: form.auth_method === 'private_key' ? form.private_key_pem : undefined,
          remote_base_path: form.remote_base_path.trim(),
          is_active: form.is_active,
        };
        saved = await api.admin.sftpConnections.create(body);
        showToast(`Connection "${saved.name}" created`, 'success');
      } else {
        if (!initial) throw new Error('edit mode without initial');
        const body: SftpConnectionUpdate = {
          name: form.name.trim() !== initial.name ? form.name.trim() : undefined,
          host: form.host.trim() !== initial.host ? form.host.trim() : undefined,
          port: form.port !== initial.port ? form.port : undefined,
          username: form.username.trim() !== initial.username ? form.username.trim() : undefined,
          auth_method: form.auth_method !== initial.auth_method ? form.auth_method : undefined,
          // empty string = "leave existing credential unchanged" per Phase 3 PUT semantics
          password: form.password.trim() ? form.password : undefined,
          private_key_pem: form.private_key_pem.trim() ? form.private_key_pem : undefined,
          remote_base_path: form.remote_base_path.trim() !== initial.remote_base_path
            ? form.remote_base_path.trim() : undefined,
          is_active: form.is_active !== initial.is_active ? form.is_active : undefined,
        };
        saved = await api.admin.sftpConnections.update(initial.id, body);
        showToast(`Connection "${saved.name}" updated`, 'success');
      }
      onSaved(saved, mode);
      onClose();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Save failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const inEdit = mode === 'edit';

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{inEdit ? 'Edit SFTP Connection' : 'New SFTP Connection'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Tenant Code"
            value={form.tenant_code}
            onChange={e => setField('tenant_code', e.target.value)}
            disabled={inEdit}
            helperText={inEdit
              ? 'Tenant cannot be changed; delete and recreate to move.'
              : 'e.g. jy, pw, fjl'}
            required
            fullWidth
            size="small"
          />
          <TextField
            label="Name"
            value={form.name}
            onChange={e => setField('name', e.target.value)}
            required
            fullWidth
            size="small"
            helperText="Unique within the tenant. e.g. jy-airline-sftp"
          />
          <Stack direction="row" spacing={2}>
            <TextField
              label="Host"
              value={form.host}
              onChange={e => setField('host', e.target.value)}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="Port"
              type="number"
              value={form.port}
              onChange={e => setField('port', parseInt(e.target.value, 10) || 22)}
              required
              size="small"
              sx={{ width: 100 }}
            />
          </Stack>
          <TextField
            label="Username"
            value={form.username}
            onChange={e => setField('username', e.target.value)}
            required
            fullWidth
            size="small"
          />
          <FormControl size="small">
            <FormLabel>Authentication</FormLabel>
            <RadioGroup
              row
              value={form.auth_method}
              onChange={e => setField('auth_method', e.target.value as SftpAuthMethod)}
            >
              <FormControlLabel value="password" control={<Radio size="small" />} label="Password" />
              <FormControlLabel value="private_key" control={<Radio size="small" />} label="Private key" />
            </RadioGroup>
          </FormControl>
          {form.auth_method === 'password' && (
            <TextField
              label="Password"
              type="password"
              value={form.password}
              onChange={e => setField('password', e.target.value)}
              required={!inEdit}
              fullWidth
              size="small"
              placeholder={inEdit ? 'Leave blank to keep existing credential' : ''}
              helperText={inEdit ? 'Only set to rotate the credential.' : undefined}
            />
          )}
          {form.auth_method === 'private_key' && (
            <TextField
              label="Private Key (PEM)"
              value={form.private_key_pem}
              onChange={e => setField('private_key_pem', e.target.value)}
              required={!inEdit}
              fullWidth
              multiline
              rows={6}
              size="small"
              placeholder={inEdit
                ? 'Leave blank to keep existing key'
                : '-----BEGIN PRIVATE KEY-----\n…'}
              helperText={inEdit ? 'Only set to rotate the credential.' : undefined}
              InputProps={{ sx: { fontFamily: 'monospace', fontSize: '0.8rem' } }}
            />
          )}
          <TextField
            label="Remote Base Path"
            value={form.remote_base_path}
            onChange={e => setField('remote_base_path', e.target.value)}
            required
            fullWidth
            size="small"
            helperText="Path on the SFTP server where files are picked up"
          />
          <FormControlLabel
            control={
              <Switch
                checked={form.is_active}
                onChange={e => setField('is_active', e.target.checked)}
              />
            }
            label="Active"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={submitting}
          startIcon={submitting ? <CircularProgress size={16} /> : undefined}
        >
          {inEdit ? 'Save Changes' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}


// ─── Page component ─────────────────────────────────────────

export default function SftpConnectionsPage() {
  const { session } = useSession();

  const [connections, setConnections] = useState<SftpConnection[]>([]);
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [tenantFilter, setTenantFilter] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<SftpConnection | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SftpConnection | null>(null);
  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<ToastState>({
    open: false, message: '', severity: 'info',
  });

  const showToast = useCallback((message: string, severity: ToastState['severity']) => {
    setToast({ open: true, message, severity });
  }, []);

  const fetchConnections = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.admin.sftpConnections.list({
        page,
        page_size: pageSize,
        tenant_code: tenantFilter || undefined,
        is_active: activeFilter === '' ? undefined : activeFilter === 'true',
      });
      setConnections(result.items);
      setPageInfo(result.page_info);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to load connections', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, tenantFilter, activeFilter, showToast]);

  useEffect(() => { fetchConnections(); }, [fetchConnections]);

  // Soft admin gate (route-level guard is the primary defense)
  if (!isSuperAdmin(session)) {
    return (
      <Box>
        <PageHeader
          title="SFTP Connections"
          breadcrumbs={[{ label: 'Admin' }, { label: 'SFTP Connections' }]}
        />
        <Alert severity="warning" sx={{ mt: 2 }}>
          RTS platform admin access required.
        </Alert>
      </Box>
    );
  }

  const markPending = (key: string, on: boolean) => {
    setPendingActions(prev => {
      const next = new Set(prev);
      if (on) next.add(key); else next.delete(key);
      return next;
    });
  };

  const handleTest = async (conn: SftpConnection) => {
    const key = `test:${conn.id}`;
    markPending(key, true);
    try {
      const result = await api.admin.sftpConnections.test(conn.id);
      showToast(
        `Test ${result.ok ? 'succeeded' : 'failed'} for ${conn.name}: ${result.detail}`,
        result.ok ? 'success' : 'error',
      );
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Test failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const key = `delete:${deleteTarget.id}`;
    markPending(key, true);
    try {
      await api.admin.sftpConnections.delete(deleteTarget.id);
      showToast(`Connection "${deleteTarget.name}" deleted`, 'success');
      setDeleteTarget(null);
      await fetchConnections();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Delete failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const handleSaved = async () => {
    await fetchConnections();
  };

  return (
    <Box>
      <PageHeader
        title="SFTP Connections"
        subtitle="Manage SFTP credentials for scheduled ingestion"
        breadcrumbs={[{ label: 'Admin' }, { label: 'SFTP Connections' }]}
        actions={
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="contained"
              color="primary"
              startIcon={<Add />}
              onClick={() => setCreateOpen(true)}
            >
              New Connection
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<Refresh />}
              onClick={fetchConnections}
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Tenant</InputLabel>
            <Select
              value={tenantFilter}
              label="Tenant"
              onChange={e => { setTenantFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All Tenants</MenuItem>
              <MenuItem value="jy">JY (Airline)</MenuItem>
              <MenuItem value="pw">PW (Airline)</MenuItem>
              <MenuItem value="fjl">FJL (Cruise/Ferry)</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Active</InputLabel>
            <Select
              value={activeFilter}
              label="Active"
              onChange={e => { setActiveFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">Active only</MenuItem>
              <MenuItem value="false">Inactive only</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : connections.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="text.secondary">No SFTP connections</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Create one to start scheduling ingestion pulls.
          </Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setCreateOpen(true)}
          >
            New Connection
          </Button>
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="SFTP connections">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Tenant</TableCell>
                <TableCell>Host:Port</TableCell>
                <TableCell>Auth</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {connections.map(conn => {
                const testKey = `test:${conn.id}`;
                const deleteKey = `delete:${conn.id}`;
                return (
                  <TableRow key={conn.id} hover>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                      {conn.name}
                    </TableCell>
                    <TableCell>
                      <Chip label={conn.tenant_code} size="small" />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                      {conn.host}:{conn.port}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={conn.auth_method.replace('_', ' ')}
                        size="small"
                        color={conn.auth_method === 'password' ? 'default' : 'primary'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={conn.is_active ? 'Active' : 'Inactive'}
                        size="small"
                        color={conn.is_active ? 'success' : 'default'}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {new Date(conn.updated_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        <Tooltip title="Edit">
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => setEditTarget(conn)}
                            >
                              <Edit fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Test connection">
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => handleTest(conn)}
                              disabled={pendingActions.has(testKey)}
                            >
                              {pendingActions.has(testKey)
                                ? <CircularProgress size={16} />
                                : <PlayArrow fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <span>
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => setDeleteTarget(conn)}
                              disabled={pendingActions.has(deleteKey)}
                            >
                              {pendingActions.has(deleteKey)
                                ? <CircularProgress size={16} />
                                : <DeleteOutline fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {pageInfo && (
            <TablePagination
              component="div"
              count={pageInfo.total}
              page={page - 1}
              onPageChange={(_, newPage) => setPage(newPage + 1)}
              rowsPerPage={pageSize}
              onRowsPerPageChange={e => {
                setPageSize(parseInt(e.target.value, 10));
                setPage(1);
              }}
              rowsPerPageOptions={[10, 20, 50, 100]}
            />
          )}
        </TableContainer>
      )}

      <ConnectionDialog
        open={createOpen}
        mode="create"
        initial={null}
        onClose={() => setCreateOpen(false)}
        onSaved={handleSaved}
        showToast={showToast}
      />
      <ConnectionDialog
        open={editTarget !== null}
        mode="edit"
        initial={editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={handleSaved}
        showToast={showToast}
      />

      <Dialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
      >
        <DialogTitle>Delete connection?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will permanently delete the SFTP connection
            <strong> {deleteTarget?.name}</strong>. If any schedules
            still reference it, deletion will be blocked with a 409
            and you'll need to delete those schedules first.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={handleConfirmDelete}
            disabled={
              deleteTarget !== null &&
              pendingActions.has(`delete:${deleteTarget.id}`)
            }
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={toast.open}
        autoHideDuration={6000}
        onClose={() => setToast(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={toast.severity}
          onClose={() => setToast(prev => ({ ...prev, open: false }))}
          sx={{ width: '100%' }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
