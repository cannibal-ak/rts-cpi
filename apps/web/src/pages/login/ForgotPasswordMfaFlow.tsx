/**
 * MFA-based password reset flow (Phase 4) — shown on the back face of the
 * login card. Proves identity via the authenticator (TOTP) or a recovery
 * code instead of email. Backed by /api/v1/auth/password-reset/mfa/{init,verify}.
 *
 * The reset_token returned by /init is held in component state only and is
 * NEVER persisted. The existing email flow (ForgotPasswordFlow.tsx) is left
 * in place; this component is what the login page now routes to.
 */
import React, { useState } from 'react';
import {
    Box, Button, TextField, Typography, Alert, CircularProgress, Link,
    InputAdornment, IconButton, FormControlLabel, Switch,
} from '@mui/material';
import { MailOutline, ShieldOutlined, CheckCircleOutline, Visibility, VisibilityOff } from '@mui/icons-material';
import { pwdResetMfaInit, pwdResetMfaVerify, MfaApiError } from '../../api/mfa';
import OtpInput from '../../components/common/OtpInput';

type Step = 1 | 2 | 'success';
const PASSWORD_MIN_LENGTH = 12;

interface Props {
    isDark: boolean;
    onBackToSignIn: () => void;
}

const primaryBtnSx = {
    py: 1.3, fontSize: '1rem', fontWeight: 700, textTransform: 'none' as const, borderRadius: 2,
    backgroundColor: '#1565C0', color: '#FFFFFF',
    '&:hover': { backgroundColor: '#0D47A1' },
    '&.Mui-disabled': { backgroundColor: '#1565C0', opacity: 0.6, color: '#FFFFFF' },
};

function focusFieldSx(isDark: boolean) {
    return {
        '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: isDark ? '#90CAF9' : '#1565C0', borderWidth: 2 },
        '& .MuiInputLabel-root.Mui-focused': { color: isDark ? '#90CAF9' : '#1565C0' },
    };
}

export default function ForgotPasswordMfaFlow({ isDark, onBackToSignIn }: Props) {
    const [step, setStep] = useState<Step>(1);
    const [email, setEmail] = useState('');
    const [resetToken, setResetToken] = useState('');   // in-memory only
    const [genericMsg, setGenericMsg] = useState('');
    const [isRecovery, setIsRecovery] = useState(false);
    const [code, setCode] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    async function handleInit(e?: React.FormEvent) {
        e?.preventDefault();
        setError('');
        const emailTrim = email.trim();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailTrim)) { setError('Please enter a valid email address.'); return; }
        setLoading(true);
        try {
            const r = await pwdResetMfaInit(emailTrim);
            setResetToken(r.reset_token);            // never persisted
            setGenericMsg(r.message);
            setStep(2);
        } catch (err: any) {
            setError(err instanceof MfaApiError ? err.message : 'Something went wrong. Please try again.');
        } finally {
            setLoading(false);
        }
    }

    async function handleVerify(e?: React.FormEvent) {
        e?.preventDefault();
        setError('');
        if (!code.trim()) { setError('Enter your authenticator or recovery code.'); return; }
        if (newPassword.length < PASSWORD_MIN_LENGTH) { setError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`); return; }
        if (newPassword !== confirmPassword) { setError('Passwords do not match.'); return; }
        setLoading(true);
        try {
            const r = await pwdResetMfaVerify(resetToken, code.trim(), newPassword, isRecovery);
            if (r.success) setStep('success');
            else setError(r.message || 'Could not reset password.');
        } catch (err: any) {
            // Generic by design (enumeration-safe backend).
            setError(err instanceof MfaApiError ? err.message : 'Invalid or expired reset.');
        } finally {
            setLoading(false);
        }
    }

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: 380 }}>
            {step === 1 && (
                <Box component="form" onSubmit={handleInit} noValidate>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', mx: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(21,101,192,0.15)' }}>
                        <MailOutline sx={{ color: isDark ? '#90CAF9' : '#1565C0' }} />
                    </Box>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                        Reset with authenticator
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 2.5 }}>
                        Enter your email. If the account exists and has an authenticator set up, you'll enter a code next.
                    </Typography>
                    {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}
                    <TextField label="Email Address" type="email" fullWidth autoFocus value={email}
                        onChange={(e) => setEmail(e.target.value)} placeholder="user@example.com" autoComplete="email" sx={focusFieldSx(isDark)} />
                    <Button type="submit" variant="contained" fullWidth size="large" disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null} sx={{ ...primaryBtnSx, mt: 2.5 }}>
                        {loading ? 'Continuing...' : 'Continue'}
                    </Button>
                    <BackLink onClick={onBackToSignIn} />
                </Box>
            )}

            {step === 2 && (
                <Box component="form" onSubmit={handleVerify} noValidate>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', mx: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(21,101,192,0.15)' }}>
                        <ShieldOutlined sx={{ color: isDark ? '#90CAF9' : '#1565C0' }} />
                    </Box>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                        Enter code & new password
                    </Typography>
                    {genericMsg && <Alert severity="info" sx={{ mt: 1.5, mb: 1 }}>{genericMsg}</Alert>}
                    {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

                    <FormControlLabel
                        control={<Switch checked={isRecovery} onChange={(e) => { setIsRecovery(e.target.checked); setCode(''); }} />}
                        label={<Typography variant="body2">Use a recovery code</Typography>}
                        sx={{ mb: 0.5 }}
                    />
                    {isRecovery && (
                        <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: 'text.secondary', mb: 1 }}>
                            Enter one of your recovery codes (format: xxxx-xxxx)
                        </Typography>
                    )}
                    <Box sx={{ mb: 2 }}>
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

                    <TextField label="New password" type={showPassword ? 'text' : 'password'} fullWidth value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" sx={{ ...focusFieldSx(isDark), mb: 2 }}
                        InputProps={{ endAdornment: (
                            <InputAdornment position="end">
                                <IconButton onClick={() => setShowPassword((s) => !s)} edge="end" size="small" aria-label="Toggle password visibility">
                                    {showPassword ? <VisibilityOff /> : <Visibility />}
                                </IconButton>
                            </InputAdornment>
                        ) }} />
                    <TextField label="Confirm password" type={showPassword ? 'text' : 'password'} fullWidth value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password"
                        error={confirmPassword.length > 0 && newPassword !== confirmPassword}
                        helperText={confirmPassword.length > 0 && newPassword !== confirmPassword ? 'Passwords do not match' : ' '}
                        sx={focusFieldSx(isDark)} />

                    <Button type="submit" variant="contained" fullWidth size="large" disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null} sx={primaryBtnSx}>
                        {loading ? 'Resetting...' : 'Reset password'}
                    </Button>
                    <BackLink onClick={onBackToSignIn} />
                </Box>
            )}

            {step === 'success' && (
                <Box>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', mx: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(46,125,50,0.15)' }}>
                        <CheckCircleOutline sx={{ color: '#2E7D32', fontSize: 30 }} />
                    </Box>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#A5D6A7' : '#2E7D32' }}>
                        Password reset successful
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 3 }}>
                        Your password has been updated. You can now sign in with your new credentials.
                    </Typography>
                    <Button onClick={onBackToSignIn} variant="contained" fullWidth size="large" sx={primaryBtnSx}>Back to sign in</Button>
                </Box>
            )}
        </Box>
    );
}

function BackLink({ onClick }: { onClick: () => void }) {
    return (
        <Box sx={{ mt: 2, textAlign: 'center' }}>
            <Link component="button" type="button" onClick={onClick} underline="none"
                sx={{ fontSize: 13, color: 'text.secondary', cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}>
                Back to sign in
            </Link>
        </Box>
    );
}
