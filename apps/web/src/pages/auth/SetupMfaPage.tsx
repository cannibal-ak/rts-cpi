/**
 * MFA enrollment page. Reachable from the Security settings panel AND used as
 * the forced-gate target (when a required user has no MFA yet). Flow:
 *   start (QR + manual secret) -> confirm 6-digit code -> show recovery codes
 *   ONCE (copy/download + acknowledge) -> continue.
 */
import React, { useEffect, useState } from 'react';
import {
    Box, Paper, TextField, Button, Typography, Alert, CircularProgress,
    Divider, Checkbox, FormControlLabel, Stack, useTheme,
} from '@mui/material';
import { ContentCopy, Download, CheckCircleOutline } from '@mui/icons-material';
import { QRCodeSVG } from 'qrcode.react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { mfaEnrollStart, mfaEnrollConfirm, mfaStatus, MfaApiError } from '../../api/mfa';
import OtpInput from '../../components/common/OtpInput';

type Step = 'loading' | 'start' | 'confirm' | 'recovery' | 'already';

const primaryBtnSx = {
    py: 1.2, fontWeight: 700, textTransform: 'none' as const, borderRadius: 2,
    backgroundColor: '#1565C0', color: '#FFFFFF', '&:hover': { backgroundColor: '#0D47A1' },
};

export default function SetupMfaPage() {
    const { accessToken } = useAuth();
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const required = params.get('required') === '1';
    const theme = useTheme();
    const isDark = theme.palette.mode === 'dark';

    const [step, setStep] = useState<Step>('loading');
    const [secret, setSecret] = useState('');
    const [uri, setUri] = useState('');
    const [code, setCode] = useState('');
    const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!accessToken) return;
        (async () => {
            try {
                const s = await mfaStatus(accessToken);
                setStep(s.enabled ? 'already' : 'start');
            } catch {
                setStep('start');
            }
        })();
    }, [accessToken]);

    const begin = async () => {
        if (!accessToken) return;
        setError(''); setLoading(true);
        try {
            const r = await mfaEnrollStart(accessToken);
            setSecret(r.secret);
            setUri(r.provisioning_uri);
            setStep('confirm');
        } catch (e: any) {
            setError(e instanceof MfaApiError ? e.message : 'Could not start enrollment.');
        } finally {
            setLoading(false);
        }
    };

    const confirm = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!accessToken) return;
        if (!/^\d{6}$/.test(code.trim())) { setError('Enter the 6-digit code.'); return; }
        setError(''); setLoading(true);
        try {
            const r = await mfaEnrollConfirm(accessToken, code.trim());
            setRecoveryCodes(r.recovery_codes || []);
            setStep('recovery');
        } catch (err: any) {
            setError(err instanceof MfaApiError ? err.message : 'Invalid code.');
        } finally {
            setLoading(false);
        }
    };

    const copyCodes = () => { navigator.clipboard?.writeText(recoveryCodes.join('\n')).catch(() => {}); };
    const downloadCodes = () => {
        const blob = new Blob([recoveryCodes.join('\n') + '\n'], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'altitude-ai-recovery-codes.txt';
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    };

    return (
        <Box sx={{
            minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
            background: isDark ? 'linear-gradient(135deg, #0a1020 0%, #11294d 100%)' : 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        }}>
            <Paper elevation={isDark ? 12 : 8} sx={{ width: '100%', maxWidth: 480, p: { xs: 3, sm: 4 }, borderRadius: '16px' }}>
                <Typography sx={{ fontSize: 22, fontWeight: 700, color: isDark ? '#90CAF9' : '#0D47A1', mb: 1 }}>
                    Set up two-step verification
                </Typography>

                {required && step !== 'recovery' && step !== 'already' && (
                    <Alert severity="warning" sx={{ mb: 2 }}>
                        Two-step verification is required before you can continue.
                    </Alert>
                )}
                {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

                {step === 'loading' && <Box sx={{ textAlign: 'center', py: 4 }}><CircularProgress /></Box>}

                {step === 'already' && (
                    <Box>
                        <Alert severity="success" icon={<CheckCircleOutline />} sx={{ mb: 2 }}>
                            Two-step verification is already enabled on your account.
                        </Alert>
                        <Button variant="contained" fullWidth sx={primaryBtnSx} onClick={() => navigate('/')}>Continue</Button>
                    </Box>
                )}

                {step === 'start' && (
                    <Box>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Use an authenticator app (Google Authenticator, Authy, 1Password, etc.) to add an
                            extra layer of security to your account.
                        </Typography>
                        <Button variant="contained" fullWidth sx={primaryBtnSx} disabled={loading}
                            startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null} onClick={begin}>
                            {loading ? 'Starting...' : 'Begin setup'}
                        </Button>
                    </Box>
                )}

                {step === 'confirm' && (
                    <Box component="form" onSubmit={confirm} noValidate>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Scan this QR code with your authenticator app, then enter the 6-digit code it shows.
                        </Typography>
                        <Box sx={{ display: 'flex', justifyContent: 'center', my: 2, p: 2, bgcolor: '#fff', borderRadius: 2, width: 'fit-content', mx: 'auto' }}>
                            {uri && <QRCodeSVG value={uri} size={176} includeMargin />}
                        </Box>
                        <Typography variant="caption" color="text.secondary">Can't scan? Enter this key manually:</Typography>
                        <Box sx={{ fontFamily: 'monospace', fontSize: 14, wordBreak: 'break-all', p: 1, mt: 0.5, mb: 2, borderRadius: 1, bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)' }}>
                            {secret}
                        </Box>
                        <Box sx={{ mb: 2 }}>
                            <OtpInput
                                groups={[6]}
                                charset="numeric"
                                value={code}
                                onChange={setCode}
                                autoFocus
                                ariaLabelPrefix="Authenticator code digit"
                            />
                        </Box>
                        <Button type="submit" variant="contained" fullWidth sx={primaryBtnSx} disabled={loading}
                            startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null}>
                            {loading ? 'Verifying...' : 'Verify & enable'}
                        </Button>
                    </Box>
                )}

                {step === 'recovery' && (
                    <Box>
                        <Alert severity="success" sx={{ mb: 2 }}>Two-step verification is now enabled.</Alert>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                            Save your recovery codes
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                            Each code can be used once if you lose access to your authenticator. They are shown only now.
                        </Typography>
                        <Box sx={{ fontFamily: 'monospace', fontSize: 14, p: 2, borderRadius: 1, mb: 1.5,
                            bgcolor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
                            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0.5 }}>
                            {recoveryCodes.map((c) => <span key={c}>{c}</span>)}
                        </Box>
                        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                            <Button size="small" startIcon={<ContentCopy />} onClick={copyCodes}>Copy</Button>
                            <Button size="small" startIcon={<Download />} onClick={downloadCodes}>Download</Button>
                        </Stack>
                        <Divider sx={{ mb: 1.5 }} />
                        <FormControlLabel
                            control={<Checkbox checked={saved} onChange={(e) => setSaved(e.target.checked)} />}
                            label="I've saved my recovery codes"
                        />
                        <Button variant="contained" fullWidth sx={{ ...primaryBtnSx, mt: 1 }} disabled={!saved}
                            onClick={() => navigate('/')}>
                            Continue
                        </Button>
                    </Box>
                )}
            </Paper>
        </Box>
    );
}
