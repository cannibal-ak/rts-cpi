/**
 * Three-step password reset flow shown on the back face of the login card.
 * Backed by /api/v1/auth/forgot-password, /verify-reset-code, /reset-password.
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
    Box,
    Button,
    TextField,
    Typography,
    Alert,
    CircularProgress,
    Link,
    InputAdornment,
    IconButton,
} from '@mui/material';
import {
    MailOutline,
    VpnKeyOutlined,
    LockOutlined,
    CheckCircleOutline,
    Visibility,
    VisibilityOff,
} from '@mui/icons-material';

type Step = 1 | 2 | 3 | 'success';

const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';
const CODE_TTL_SECONDS = 5 * 60;
const PASSWORD_MIN_LENGTH = 12; // matches backend validate_password_strength

interface ForgotPasswordFlowProps {
    isDark: boolean;
    onBackToSignIn: () => void;
}

export default function ForgotPasswordFlow({ isDark, onBackToSignIn }: ForgotPasswordFlowProps) {
    const [step, setStep] = useState<Step>(1);
    const [email, setEmail] = useState('');
    const [codeDigits, setCodeDigits] = useState<string[]>(['', '', '', '', '', '']);
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showNewPassword, setShowNewPassword] = useState(false);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [shake, setShake] = useState(false);

    // Code expiry timer (5 minutes). Set when step 1 succeeds.
    const [secondsLeft, setSecondsLeft] = useState(CODE_TTL_SECONDS);
    const expiryRef = useRef<number | null>(null);

    // Refs for the 6 digit boxes (auto-advance + paste support).
    const digitRefs = useRef<(HTMLInputElement | null)[]>([]);

    useEffect(() => {
        if (step !== 2 || expiryRef.current === null) return;
        const tick = () => {
            const remaining = Math.max(0, Math.ceil((expiryRef.current! - Date.now()) / 1000));
            setSecondsLeft(remaining);
        };
        tick();
        const id = window.setInterval(tick, 1000);
        return () => window.clearInterval(id);
    }, [step]);

    const codeExpired = step === 2 && secondsLeft === 0;
    const code = codeDigits.join('');

    const passwordScore = useMemo(() => {
        let score = 0;
        if (newPassword.length >= 8) score++;
        if (/[A-Z]/.test(newPassword)) score++;
        if (/\d/.test(newPassword)) score++;
        if (/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/.test(newPassword)) score++;
        return score;
    }, [newPassword]);

    const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

    // ── API calls ──────────────────────────────────

    async function callForgot(emailValue: string): Promise<{ ok: boolean; message: string }> {
        try {
            const res = await fetch(`${API_BASE}/api/v1/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailValue.trim().toLowerCase() }),
            });
            if (!res.ok) {
                return { ok: false, message: 'Connection error. Please try again.' };
            }
            const data = await res.json();
            return { ok: !!data.success, message: data.message || '' };
        } catch {
            return { ok: false, message: 'Connection error. Please try again.' };
        }
    }

    async function callVerify(emailValue: string, codeValue: string) {
        try {
            const res = await fetch(`${API_BASE}/api/v1/auth/verify-reset-code`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailValue.trim().toLowerCase(), code: codeValue }),
            });
            if (!res.ok) return { ok: false, message: 'Connection error. Please try again.' };
            const data = await res.json();
            return { ok: !!data.success, message: data.message || '' };
        } catch {
            return { ok: false, message: 'Connection error. Please try again.' };
        }
    }

    async function callReset(emailValue: string, codeValue: string, password: string) {
        try {
            const res = await fetch(`${API_BASE}/api/v1/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: emailValue.trim().toLowerCase(),
                    code: codeValue,
                    new_password: password,
                }),
            });
            if (!res.ok) return { ok: false, message: 'Connection error. Please try again.' };
            const data = await res.json();
            return { ok: !!data.success, message: data.message || '' };
        } catch {
            return { ok: false, message: 'Connection error. Please try again.' };
        }
    }

    // ── Step transitions ───────────────────────────

    function startExpiryTimer() {
        expiryRef.current = Date.now() + CODE_TTL_SECONDS * 1000;
        setSecondsLeft(CODE_TTL_SECONDS);
    }

    async function handleSendCode(e?: React.FormEvent) {
        e?.preventDefault();
        setError('');
        const emailTrim = email.trim();
        if (!emailTrim) {
            setError('Please enter your email address.');
            return;
        }
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailTrim)) {
            setError('Please enter a valid email address.');
            return;
        }
        setLoading(true);
        const r = await callForgot(emailTrim);
        setLoading(false);
        if (!r.ok) {
            setError(r.message || 'Something went wrong. Please try again.');
            return;
        }
        startExpiryTimer();
        setCodeDigits(['', '', '', '', '', '']);
        setStep(2);
    }

    async function handleResend() {
        setError('');
        setLoading(true);
        const r = await callForgot(email);
        setLoading(false);
        if (!r.ok) {
            setError(r.message || 'Could not resend code.');
            return;
        }
        startExpiryTimer();
        setCodeDigits(['', '', '', '', '', '']);
        digitRefs.current[0]?.focus();
    }

    async function handleVerify(e?: React.FormEvent) {
        e?.preventDefault();
        setError('');
        if (code.length !== 6) {
            setError('Please enter all 6 digits.');
            return;
        }
        if (codeExpired) {
            setError('Code expired. Please request a new one.');
            return;
        }
        setLoading(true);
        const r = await callVerify(email, code);
        setLoading(false);
        if (!r.ok) {
            setError(r.message || 'Invalid code.');
            setShake(true);
            window.setTimeout(() => setShake(false), 450);
            return;
        }
        setStep(3);
    }

    async function handleReset(e?: React.FormEvent) {
        e?.preventDefault();
        setError('');
        if (newPassword.length < PASSWORD_MIN_LENGTH) {
            setError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`);
            return;
        }
        if (newPassword !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }
        setLoading(true);
        const r = await callReset(email, code, newPassword);
        setLoading(false);
        if (!r.ok) {
            setError(r.message || 'Could not reset password.');
            return;
        }
        setStep('success');
    }

    // ── Digit box input handling ───────────────────

    function handleDigitChange(idx: number, raw: string) {
        // If user pasted multiple chars, distribute.
        const digits = raw.replace(/\D/g, '');
        if (digits.length === 0) {
            const next = [...codeDigits];
            next[idx] = '';
            setCodeDigits(next);
            return;
        }
        if (digits.length > 1) {
            const next = [...codeDigits];
            for (let i = 0; i < digits.length && idx + i < 6; i++) {
                next[idx + i] = digits[i];
            }
            setCodeDigits(next);
            const lastFilled = Math.min(idx + digits.length, 5);
            digitRefs.current[lastFilled]?.focus();
            return;
        }
        const next = [...codeDigits];
        next[idx] = digits[0];
        setCodeDigits(next);
        if (idx < 5) digitRefs.current[idx + 1]?.focus();
    }

    function handleDigitKeyDown(idx: number, e: React.KeyboardEvent<HTMLInputElement>) {
        if (e.key === 'Backspace' && !codeDigits[idx] && idx > 0) {
            digitRefs.current[idx - 1]?.focus();
        }
    }

    // ── Render helpers ─────────────────────────────

    const maskedEmail = email && email.includes('@')
        ? `${email[0]}***@${email.split('@')[1]}`
        : email;

    const minsLeft = Math.floor(secondsLeft / 60);
    const secsLeft = secondsLeft % 60;
    const timerText = `${minsLeft}:${secsLeft.toString().padStart(2, '0')}`;

    // ── UI ─────────────────────────────────────────

    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: 380 }}>
            {/* Step indicator (hidden on success) */}
            {step !== 'success' && (
                <StepIndicator activeStep={step as 1 | 2 | 3} isDark={isDark} />
            )}

            {step === 1 && (
                <Box component="form" onSubmit={handleSendCode} noValidate>
                    <IconCircle color={isDark ? '#1565C0' : '#1565C0'} bgAlpha={0.15}>
                        <MailOutline sx={{ color: isDark ? '#90CAF9' : '#1565C0' }} />
                    </IconCircle>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                        Reset your password
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 2.5 }}>
                        Enter the email address associated with your account. We'll send a 6-digit verification code.
                    </Typography>

                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
                            {error}
                        </Alert>
                    )}

                    <TextField
                        label="Email Address"
                        type="email"
                        fullWidth
                        autoFocus
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="user@example.com"
                        autoComplete="email"
                        sx={focusFieldSx(isDark)}
                    />

                    <Button
                        type="submit"
                        variant="contained"
                        fullWidth
                        size="large"
                        disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null}
                        sx={{ ...primaryBtnSx, mt: 2.5 }}
                    >
                        {loading ? 'Sending...' : 'Send verification code'}
                    </Button>

                    <BackToSignInLink onClick={onBackToSignIn} />
                </Box>
            )}

            {step === 2 && (
                <Box component="form" onSubmit={handleVerify} noValidate>
                    <IconCircle color="#FFA000" bgAlpha={0.15}>
                        <VpnKeyOutlined sx={{ color: '#FFA000' }} />
                    </IconCircle>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                        Enter verification code
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 2 }}>
                        We sent a 6-digit code to <strong>{maskedEmail}</strong>
                    </Typography>

                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
                            {error}
                        </Alert>
                    )}

                    <Box
                        sx={{
                            display: 'flex',
                            justifyContent: 'center',
                            gap: 1,
                            mb: 1.5,
                            animation: shake ? 'codeShake 400ms cubic-bezier(.36,.07,.19,.97)' : 'none',
                            '@keyframes codeShake': {
                                '10%, 90%': { transform: 'translateX(-2px)' },
                                '20%, 80%': { transform: 'translateX(4px)' },
                                '30%, 50%, 70%': { transform: 'translateX(-6px)' },
                                '40%, 60%': { transform: 'translateX(6px)' },
                            },
                        }}
                    >
                        {codeDigits.map((d, i) => (
                            <TextField
                                key={i}
                                inputRef={(el) => { digitRefs.current[i] = el; }}
                                value={d}
                                onChange={(e) => handleDigitChange(i, e.target.value)}
                                onKeyDown={(e) => handleDigitKeyDown(i, e as React.KeyboardEvent<HTMLInputElement>)}
                                inputProps={{
                                    maxLength: 6, // allow paste of full code into any box
                                    inputMode: 'numeric',
                                    pattern: '[0-9]*',
                                    style: { textAlign: 'center', fontSize: 22, fontWeight: 700, padding: '10px 0' },
                                    'aria-label': `Digit ${i + 1}`,
                                }}
                                autoFocus={i === 0}
                                sx={{ width: 44, '& .MuiOutlinedInput-root': { ...focusFieldSx(isDark)['& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline'] && {} } }}
                            />
                        ))}
                    </Box>

                    <Typography
                        sx={{
                            fontSize: 13,
                            textAlign: 'center',
                            color: codeExpired ? '#E53935' : '#FFA000',
                            fontWeight: 600,
                            mb: 2,
                        }}
                    >
                        {codeExpired ? 'Code expired. Please request a new one.' : `Code expires in ${timerText}`}
                    </Typography>

                    <Button
                        type="submit"
                        variant="contained"
                        fullWidth
                        size="large"
                        disabled={loading || codeExpired}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null}
                        sx={primaryBtnSx}
                    >
                        {loading ? 'Verifying...' : 'Verify code'}
                    </Button>

                    <Box sx={{ mt: 1.5, textAlign: 'center' }}>
                        <Typography variant="body2" component="span" color="text.secondary">
                            Didn't receive a code?{' '}
                        </Typography>
                        <Link
                            component="button"
                            type="button"
                            onClick={handleResend}
                            sx={{
                                fontSize: 13,
                                fontWeight: 600,
                                color: isDark ? '#90CAF9' : '#1565C0',
                                cursor: 'pointer',
                            }}
                        >
                            Resend
                        </Link>
                    </Box>

                    <BackToSignInLink onClick={onBackToSignIn} />
                </Box>
            )}

            {step === 3 && (
                <Box component="form" onSubmit={handleReset} noValidate>
                    <IconCircle color={isDark ? '#1565C0' : '#1565C0'} bgAlpha={0.15}>
                        <LockOutlined sx={{ color: isDark ? '#90CAF9' : '#1565C0' }} />
                    </IconCircle>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#90CAF9' : '#0D47A1' }}>
                        Set new password
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 2 }}>
                        Must be at least {PASSWORD_MIN_LENGTH} characters with uppercase, lowercase, number, and special character.
                    </Typography>

                    {error && (
                        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
                            {error}
                        </Alert>
                    )}

                    <TextField
                        label="New password"
                        type={showNewPassword ? 'text' : 'password'}
                        fullWidth
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        autoComplete="new-password"
                        autoFocus
                        sx={{ ...focusFieldSx(isDark), mb: 1 }}
                        InputProps={{
                            endAdornment: (
                                <InputAdornment position="end">
                                    <IconButton onClick={() => setShowNewPassword((s) => !s)} edge="end" size="small" aria-label="Toggle password visibility">
                                        {showNewPassword ? <VisibilityOff /> : <Visibility />}
                                    </IconButton>
                                </InputAdornment>
                            ),
                        }}
                    />

                    <StrengthBar score={passwordScore} isDark={isDark} hasInput={newPassword.length > 0} />

                    <TextField
                        label="Confirm password"
                        type={showNewPassword ? 'text' : 'password'}
                        fullWidth
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        autoComplete="new-password"
                        sx={{ ...focusFieldSx(isDark), mt: 1.5 }}
                        helperText={confirmPassword.length > 0 && !passwordsMatch ? 'Passwords do not match' : ' '}
                        error={confirmPassword.length > 0 && !passwordsMatch}
                    />

                    <Button
                        type="submit"
                        variant="contained"
                        fullWidth
                        size="large"
                        disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} color="inherit" /> : null}
                        sx={{ ...primaryBtnSx, mt: 1 }}
                    >
                        {loading ? 'Resetting...' : 'Reset password'}
                    </Button>

                    <BackToSignInLink onClick={onBackToSignIn} />
                </Box>
            )}

            {step === 'success' && (
                <Box>
                    <IconCircle color="#2E7D32" bgAlpha={0.15}>
                        <CheckCircleOutline sx={{ color: '#2E7D32', fontSize: 32 }} />
                    </IconCircle>
                    <Typography sx={{ fontSize: 22, fontWeight: 700, textAlign: 'center', mt: 2, color: isDark ? '#A5D6A7' : '#2E7D32' }}>
                        Password reset successful
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 1, mb: 3 }}>
                        Your password has been updated. You can now sign in with your new credentials.
                    </Typography>

                    <Button
                        onClick={onBackToSignIn}
                        variant="contained"
                        fullWidth
                        size="large"
                        sx={primaryBtnSx}
                    >
                        Back to sign in
                    </Button>
                </Box>
            )}
        </Box>
    );
}

// ── Sub-components ────────────────────────────────

function StepIndicator({ activeStep, isDark }: { activeStep: 1 | 2 | 3; isDark: boolean }) {
    const inactiveColor = isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)';
    const activeColor = isDark ? '#90CAF9' : '#1565C0';
    return (
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.75, mb: 2.5 }}>
            {[1, 2, 3].map((n) => {
                const isActive = n === activeStep;
                return (
                    <Box
                        key={n}
                        sx={{
                            height: 6,
                            width: isActive ? 24 : 6,
                            borderRadius: 3,
                            backgroundColor: isActive ? activeColor : inactiveColor,
                            transition: 'all 250ms ease',
                        }}
                    />
                );
            })}
        </Box>
    );
}

function IconCircle({ color, bgAlpha, children }: { color: string; bgAlpha: number; children: React.ReactNode }) {
    // Convert hex to rgba background.
    const hex = color.replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    return (
        <Box
            sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                backgroundColor: `rgba(${r},${g},${b},${bgAlpha})`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mx: 'auto',
                '& > svg': { fontSize: 26 },
            }}
        >
            {children}
        </Box>
    );
}

function StrengthBar({ score, isDark, hasInput }: { score: number; isDark: boolean; hasInput: boolean }) {
    const segments = [0, 1, 2, 3];
    let label = '';
    let color = isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.12)';
    if (hasInput) {
        if (score <= 1) { label = 'Weak'; color = '#E53935'; }
        else if (score === 2) { label = 'Fair'; color = '#FB8C00'; }
        else if (score === 3) { label = 'Medium'; color = '#FFA000'; }
        else { label = 'Strong'; color = '#2E7D32'; }
    }
    return (
        <Box sx={{ mt: 0.5 }}>
            <Box sx={{ display: 'flex', gap: 0.5 }}>
                {segments.map((i) => (
                    <Box
                        key={i}
                        sx={{
                            flex: 1,
                            height: 4,
                            borderRadius: 2,
                            backgroundColor: hasInput && i < score ? color : (isDark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.08)'),
                            transition: 'background-color 150ms ease',
                        }}
                    />
                ))}
            </Box>
            {hasInput && (
                <Typography sx={{ fontSize: 11, mt: 0.5, color, fontWeight: 600, letterSpacing: '0.05em' }}>
                    {label}
                </Typography>
            )}
        </Box>
    );
}

function BackToSignInLink({ onClick }: { onClick: () => void }) {
    return (
        <Box sx={{ mt: 2, textAlign: 'center' }}>
            <Link
                component="button"
                type="button"
                onClick={onClick}
                underline="none"
                sx={{
                    fontSize: 13,
                    color: 'text.secondary',
                    cursor: 'pointer',
                    '&:hover': { textDecoration: 'underline' },
                }}
            >
                Back to sign in
            </Link>
        </Box>
    );
}

// ── Shared style helpers ──────────────────────────

const primaryBtnSx = {
    py: 1.3,
    fontSize: '1rem',
    fontWeight: 700,
    textTransform: 'none' as const,
    borderRadius: 2,
    backgroundColor: '#1565C0',
    color: '#FFFFFF',
    '&:hover': { backgroundColor: '#0D47A1' },
    '&.Mui-disabled': { backgroundColor: '#1565C0', opacity: 0.6, color: '#FFFFFF' },
};

function focusFieldSx(isDark: boolean) {
    return {
        '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
            borderColor: isDark ? '#90CAF9' : '#1565C0',
            borderWidth: 2,
        },
        '& .MuiInputLabel-root.Mui-focused': {
            color: isDark ? '#90CAF9' : '#1565C0',
        },
    };
}
