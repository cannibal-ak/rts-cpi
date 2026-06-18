/**
 * Security settings — two-step verification status + disable.
 *
 * NOTE: there is no "regenerate recovery codes" action — the backend has no
 * endpoint for it. Refreshing codes is currently disable + re-enroll. Deferred.
 */
import React, { useEffect, useState } from 'react';
import {
    Box, Paper, Typography, Button, Chip, Alert, CircularProgress, Divider,
    Dialog, DialogTitle, DialogContent, DialogActions, TextField, Stack,
} from '@mui/material';
import { ShieldOutlined } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { mfaStatus, mfaDisable, MfaApiError } from '../../api/mfa';
import type { MfaStatus } from '../../api/mfa';

export default function SecurityPage() {
    const { accessToken } = useAuth();
    const navigate = useNavigate();
    const [status, setStatus] = useState<MfaStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [disableOpen, setDisableOpen] = useState(false);
    const [password, setPassword] = useState('');
    const [code, setCode] = useState('');
    const [disabling, setDisabling] = useState(false);
    const [disableError, setDisableError] = useState('');

    const load = async () => {
        if (!accessToken) return;
        setLoading(true); setError('');
        try {
            setStatus(await mfaStatus(accessToken));
        } catch (e: any) {
            setError(e instanceof MfaApiError ? e.message : 'Could not load security status.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [accessToken]);

    const handleDisable = async () => {
        if (!accessToken) return;
        setDisableError(''); setDisabling(true);
        try {
            await mfaDisable(accessToken, password, code.trim());
            setDisableOpen(false);
            setPassword(''); setCode('');
            await load();
        } catch (e: any) {
            setDisableError(e instanceof MfaApiError ? e.message : 'Could not disable.');
        } finally {
            setDisabling(false);
        }
    };

    return (
        <Box sx={{ p: 3, maxWidth: 720, mx: 'auto' }}>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 2 }}>Security</Typography>

            <Paper variant="outlined" sx={{ p: 3 }}>
                <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
                    <ShieldOutlined color="primary" />
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>Two-step verification</Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Protect your account with a time-based code from an authenticator app.
                </Typography>

                {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

                {loading ? (
                    <Box sx={{ py: 3, textAlign: 'center' }}><CircularProgress size={24} /></Box>
                ) : status ? (
                    <Box>
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                            <Typography variant="body2">Status:</Typography>
                            <Chip size="small" label={status.enabled ? 'Enabled' : 'Disabled'}
                                color={status.enabled ? 'success' : 'default'} />
                            {status.exempt && <Chip size="small" label="Exempt" variant="outlined" />}
                        </Stack>
                        {status.enabled && (
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                Recovery codes remaining: <strong>{status.recovery_codes_remaining}</strong>
                            </Typography>
                        )}

                        <Divider sx={{ my: 2 }} />

                        {status.enabled ? (
                            <Button variant="outlined" color="error" onClick={() => setDisableOpen(true)}>
                                Disable two-step verification
                            </Button>
                        ) : (
                            <Button variant="contained" onClick={() => navigate('/setup-mfa')}>
                                Set up two-step verification
                            </Button>
                        )}
                    </Box>
                ) : null}
            </Paper>

            <Dialog open={disableOpen} onClose={() => !disabling && setDisableOpen(false)} fullWidth maxWidth="xs">
                <DialogTitle>Disable two-step verification</DialogTitle>
                <DialogContent>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        Confirm your password and a current authenticator code to turn off two-step verification.
                    </Typography>
                    {disableError && <Alert severity="error" sx={{ mb: 2 }}>{disableError}</Alert>}
                    <TextField label="Password" type="password" fullWidth value={password}
                        onChange={(e) => setPassword(e.target.value)} sx={{ mb: 2 }} autoComplete="current-password" />
                    <TextField label="Authenticator code" fullWidth value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                        inputProps={{ inputMode: 'numeric', maxLength: 6 }} />
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDisableOpen(false)} disabled={disabling}>Cancel</Button>
                    <Button onClick={handleDisable} color="error" variant="contained" disabled={disabling || !password || code.length !== 6}>
                        {disabling ? 'Disabling...' : 'Disable'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
}
