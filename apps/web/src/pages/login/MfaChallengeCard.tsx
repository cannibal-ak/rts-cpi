/**
 * Two-step login challenge card. Rendered by LoginPage when AuthContext has
 * an active mfa_challenge (in-memory). On success AuthContext sets the user
 * and LoginPage re-renders into its normal post-login redirect.
 */
import React, { useState } from 'react';
import {
    Box, Paper, TextField, Button, Typography, Alert, CircularProgress, Link, useTheme,
} from '@mui/material';
import { ShieldOutlined } from '@mui/icons-material';
import OtpInput from '../../components/common/OtpInput';

interface Props {
    verifyMfa: (code: string, isRecovery?: boolean) => Promise<{ success: boolean; error?: string }>;
    onCancel: () => void;
}

const primaryBtnSx = {
    py: 1.3, fontSize: '1rem', fontWeight: 700, textTransform: 'none' as const, borderRadius: 2,
    backgroundColor: '#1565C0', color: '#FFFFFF',
    '&:hover': { backgroundColor: '#0D47A1' },
    '&.Mui-disabled': { backgroundColor: '#1565C0', opacity: 0.6, color: '#FFFFFF' },
};

export default function MfaChallengeCard({ verifyMfa, onCancel }: Props) {
    const theme = useTheme();
    const isDark = theme.palette.mode === 'dark';
    const [isRecovery, setIsRecovery] = useState(false);
    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        const value = code.trim();
        if (!isRecovery && !/^\d{6}$/.test(value)) {
            setError('Enter the 6-digit code from your authenticator.');
            return;
        }
        if (isRecovery && value.length < 6) {
            setError('Enter one of your recovery codes.');
            return;
        }
        setLoading(true);
        const r = await verifyMfa(value, isRecovery);
        setLoading(false);
        // On success AuthContext sets the user → LoginPage redirects; nothing to do here.
        if (!r.success) setError(r.error || 'Invalid code.');
    };

    return (
        <Box sx={{
            minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 2,
            background: isDark
                ? 'linear-gradient(135deg, #0a1020 0%, #0f1f3a 50%, #11294d 100%)'
                : 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        }}>
            <Paper elevation={isDark ? 12 : 8} sx={{
                width: '100%', maxWidth: 440, p: { xs: 3, sm: 5 }, borderRadius: '16px', textAlign: 'center',
                backgroundColor: isDark ? 'rgba(20,30,50,0.92)' : 'rgba(255,255,255,0.98)',
            }}>
                <Box sx={{
                    width: 48, height: 48, borderRadius: '50%', mx: 'auto', mb: 2,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    backgroundColor: isDark ? 'rgba(144,202,249,0.15)' : 'rgba(21,101,192,0.12)',
                }}>
                    <ShieldOutlined sx={{ color: isDark ? '#90CAF9' : '#1565C0', fontSize: 26 }} />
                </Box>
                <Typography sx={{ fontSize: 22, fontWeight: 700, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                    Two-step verification
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 2.5 }}>
                    {isRecovery
                        ? 'Enter one of your saved recovery codes.'
                        : 'Enter the 6-digit code from your authenticator app.'}
                </Typography>

                {error && <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }} onClose={() => setError('')}>{error}</Alert>}

                <Box component="form" onSubmit={handleSubmit} noValidate>
                    {isRecovery && (
                        <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: 'text.secondary', mb: 1 }}>
                            Enter one of your recovery codes (format: xxxx-xxxx)
                        </Typography>
                    )}
                    <Box sx={{ mb: 2.5 }}>
                        <OtpInput
                            key={isRecovery ? 'recovery' : 'totp'}
                            groups={isRecovery ? [4, 4] : [6]}
                            charset={isRecovery ? 'hex' : 'numeric'}
                            value={code}
                            onChange={setCode}
                            autoFocus
                            ariaLabelPrefix={isRecovery ? 'Recovery code character' : 'Authenticator code digit'}
                        />
                    </Box>
                    <Button type="submit" variant="contained" fullWidth size="large" disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null} sx={primaryBtnSx}>
                        {loading ? 'Verifying...' : 'Verify'}
                    </Button>
                </Box>

                <Box sx={{ mt: 2 }}>
                    <Link component="button" type="button" underline="none"
                        onClick={() => { setIsRecovery((v) => !v); setCode(''); setError(''); }}
                        sx={{ fontSize: 13, color: isDark ? '#90CAF9' : '#1565C0', cursor: 'pointer' }}>
                        {isRecovery ? 'Use an authenticator code instead' : 'Use a recovery code'}
                    </Link>
                </Box>
                <Box sx={{ mt: 1.5 }}>
                    <Link component="button" type="button" underline="none" onClick={onCancel}
                        sx={{ fontSize: 13, color: 'text.secondary', cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}>
                        Back to sign in
                    </Link>
                </Box>
            </Paper>
        </Box>
    );
}
