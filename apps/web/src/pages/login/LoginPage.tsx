import React, { useState } from 'react';
import {
    Box,
    Paper,
    TextField,
    Button,
    Typography,
    Alert,
    CircularProgress,
    InputAdornment,
    IconButton,
    Link,
    Tooltip,
    useTheme,
} from '@mui/material';
import { Visibility, VisibilityOff, LockOutlined, DarkMode, LightMode } from '@mui/icons-material';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useSession } from '../../context/SessionContext';
import { useThemeMode } from '../../context/ThemeContext';
import ForgotPasswordMfaFlow from './ForgotPasswordMfaFlow';
import MfaChallengeCard from './MfaChallengeCard';



export default function LoginPage() {
    const { login, isAuthenticated, mustChangePassword, mfaChallengeActive, verifyMfa, cancelMfaChallenge } = useAuth();
    const { session, isSyncing } = useSession();
    const navigate = useNavigate();
    const theme = useTheme();
    const { toggleTheme } = useThemeMode();

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    // Card flip: false = login (front), true = forgot password (back).
    const [flipped, setFlipped] = useState(false);
    // Bumping this key remounts ForgotPasswordFlow, clearing all step state.
    const [resetFlowKey, setResetFlowKey] = useState(0);

    const flipToReset = () => setFlipped(true);
    const flipToLogin = () => {
        setFlipped(false);
        // Reset back-face state after the flip animation completes.
        window.setTimeout(() => setResetFlowKey((k) => k + 1), 650);
    };

    // If already logged in, redirect appropriately
    if (isAuthenticated) {
        if (mustChangePassword) return <Navigate to="/change-password" replace />;

        if (isSyncing) {
            return (
                <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CircularProgress />
                </Box>
            );
        }

        if (session.user.roles.includes('TENANT_ADMIN')) return <Navigate to="/" replace />;
        return <Navigate to="/dashboards" replace />;
    }

    // Two-step MFA: AuthContext holds an in-memory challenge -> show the card.
    if (mfaChallengeActive) {
        return <MfaChallengeCard verifyMfa={verifyMfa} onCancel={cancelMfaChallenge} />;
    }

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!email.trim()) {
            setError('Please enter your email address');
            return;
        }
        if (!password) {
            setError('Please enter your password');
            return;
        }

        setLoading(true);
        const result = await login(email, password);
        setLoading(false);

        if (!result.success && !result.mfaRequired) {
            setError(result.error || 'Login failed');
        }
        // On success, AuthContext updates state → re-render → Navigate triggers above
    };

    const isDark = theme.palette.mode === 'dark';
    const gridStroke = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(13,71,161,0.05)';
    const gridSvg = `url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40' viewBox='0 0 40 40'><path d='M40 0H0v40' fill='none' stroke='${encodeURIComponent(gridStroke)}' stroke-width='1'/></svg>")`;
    const footerColor1 = isDark ? 'rgba(255,255,255,0.40)' : 'rgba(0,0,0,0.35)';
    const footerColor2 = isDark ? 'rgba(255,255,255,0.30)' : 'rgba(0,0,0,0.28)';
    const footerLinkHover = isDark ? 'rgba(255,255,255,0.55)' : 'rgba(0,0,0,0.55)';
    const year = new Date().getFullYear();

    return (
        <Box
            sx={{
                minHeight: '100vh',
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                overflow: 'hidden',
                background: isDark
                    ? 'linear-gradient(135deg, #0a1020 0%, #0f1f3a 50%, #11294d 100%)'
                    : 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
                '&::before': {
                    content: '""',
                    position: 'absolute',
                    inset: 0,
                    backgroundImage: gridSvg,
                    backgroundSize: '40px 40px',
                    pointerEvents: 'none',
                    zIndex: 0,
                },
                '&::after': {
                    content: '""',
                    position: 'absolute',
                    inset: 0,
                    background: isDark
                        ? 'radial-gradient(circle at 18% 20%, rgba(80,140,220,0.10) 0%, transparent 45%), radial-gradient(circle at 82% 78%, rgba(120,80,200,0.08) 0%, transparent 50%)'
                        : 'radial-gradient(circle at 18% 20%, rgba(120,160,220,0.18) 0%, transparent 45%), radial-gradient(circle at 82% 78%, rgba(200,210,235,0.20) 0%, transparent 50%)',
                    pointerEvents: 'none',
                    zIndex: 0,
                },
                '@keyframes loginCardFadeIn': {
                    from: { opacity: 0, transform: 'translateY(8px)' },
                    to: { opacity: 1, transform: 'translateY(0)' },
                },
            }}
        >
            {/* Theme toggle — top-right corner, floats above background */}
            <Tooltip title={`Switch to ${isDark ? 'light' : 'dark'} mode`}>
                <IconButton
                    onClick={toggleTheme}
                    aria-label="Toggle theme"
                    sx={{
                        position: 'absolute',
                        top: 16,
                        right: 16,
                        zIndex: 2,
                        color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)',
                        '&:hover': {
                            color: isDark ? 'rgba(255,255,255,0.9)' : 'rgba(0,0,0,0.8)',
                            backgroundColor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
                        },
                        '& .MuiSvgIcon-root': { fontSize: 22 },
                    }}
                >
                    {isDark ? <LightMode /> : <DarkMode />}
                </IconButton>
            </Tooltip>

            {/* Card region (centered, takes remaining space) */}
            <Box
                sx={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    p: 2,
                    position: 'relative',
                    zIndex: 1,
                }}
            >
            {/* 3D flip scene — wraps front (login) and back (forgot password) faces */}
            <Box
                sx={{
                    perspective: '1200px',
                    width: '100%',
                    maxWidth: 440,
                    animation: 'loginCardFadeIn 450ms ease-out',
                }}
            >
            <Box
                sx={{
                    position: 'relative',
                    width: '100%',
                    transformStyle: 'preserve-3d',
                    transition: 'transform 0.6s cubic-bezier(0.4, 0, 0.2, 1)',
                    transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)',
                }}
            >
            <Paper
                elevation={isDark ? 12 : 8}
                aria-hidden={flipped}
                sx={{
                    width: '100%',
                    p: { xs: 3, sm: 5 },
                    borderRadius: '16px',
                    textAlign: 'center',
                    backgroundColor: isDark ? 'rgba(20,30,50,0.92)' : 'rgba(255,255,255,0.98)',
                    backdropFilter: 'blur(8px)',
                    border: isDark ? '1px solid rgba(255,255,255,0.06)' : '1px solid rgba(13,71,161,0.06)',
                    boxShadow: isDark
                        ? '0 20px 60px rgba(0,0,0,0.45), 0 2px 8px rgba(0,0,0,0.3)'
                        : '0 20px 60px rgba(13,71,161,0.12), 0 2px 8px rgba(0,0,0,0.06)',
                    backfaceVisibility: 'hidden',
                    WebkitBackfaceVisibility: 'hidden',
                    pointerEvents: flipped ? 'none' : 'auto',
                }}
            >
                {/* Logo */}
                <Box sx={{ mb: 3 }}>
                    <Box
                        component="img"
                        src="/assets/RTS_Logo.png"
                        alt="RTS Logo"
                        onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
                            const img = e.currentTarget;
                            if (img.src.endsWith('.png')) {
                                img.src = '/assets/RTS_Logo.svg';
                            } else {
                                img.style.display = 'none';
                            }
                        }}
                        sx={{
                            height: 56,
                            mb: 1.5,
                            filter: theme.palette.mode === 'dark' ? 'brightness(0) invert(1)' : 'none',
                            transition: 'filter 200ms ease',
                        }}
                    />
                    <Typography
                        component="h1"
                        sx={{
                            fontSize: '32px',
                            fontWeight: 700,
                            lineHeight: 1.1,
                            color: isDark ? '#00BCD4' : '#0D47A1',
                            letterSpacing: '-0.01em',
                        }}
                    >
                        Altitude AI
                    </Typography>
                    <Typography
                        sx={{
                            mt: 1,
                            fontSize: '11px',
                            fontWeight: 600,
                            letterSpacing: '0.18em',
                            textTransform: 'uppercase',
                            color: isDark ? '#00BCD4' : 'rgba(13,71,161,0.7)',
                        }}
                    >
                        Market Intelligence Platform
                    </Typography>
                    <Box
                        sx={{
                            width: 32,
                            height: 2,
                            mx: 'auto',
                            mt: 1,
                            mb: 1.5,
                            borderRadius: 1,
                            background: isDark
                                ? 'linear-gradient(90deg, #00BCD4 0%, #4DD0E1 100%)'
                                : '#1565C0',
                            opacity: 0.7,
                        }}
                    />
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                        Sign in to your account to continue
                    </Typography>
                </Box>

                {/* Error */}
                {error && (
                    <Alert severity="error" sx={{ mb: 2, textAlign: 'left' }} onClose={() => setError('')}>
                        {error}
                    </Alert>
                )}

                {/* Form */}
                <Box component="form" onSubmit={handleSubmit} noValidate>


                    <TextField
                        id="login-email"
                        label="Email Address"
                        type="email"
                        fullWidth
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="user@example.com"
                        autoComplete="email"
                        autoFocus
                        sx={{
                            mb: 2,
                            '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
                                borderColor: isDark ? '#90CAF9' : '#1565C0',
                                borderWidth: 2,
                            },
                            '& .MuiInputLabel-root.Mui-focused': {
                                color: isDark ? '#90CAF9' : '#1565C0',
                            },
                        }}
                    />

                    <TextField
                        id="login-password"
                        label="Password"
                        type={showPassword ? 'text' : 'password'}
                        fullWidth
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Enter password"
                        autoComplete="current-password"
                        sx={{
                            mb: 2.5,
                            '& .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline': {
                                borderColor: isDark ? '#90CAF9' : '#1565C0',
                                borderWidth: 2,
                            },
                            '& .MuiInputLabel-root.Mui-focused': {
                                color: isDark ? '#90CAF9' : '#1565C0',
                            },
                        }}
                        InputProps={{
                            endAdornment: (
                                <InputAdornment position="end">
                                    <IconButton
                                        aria-label="Toggle password visibility"
                                        onClick={() => setShowPassword(!showPassword)}
                                        edge="end"
                                        size="small"
                                    >
                                        {showPassword ? <VisibilityOff /> : <Visibility />}
                                    </IconButton>
                                </InputAdornment>
                            ),
                        }}
                    />

                    <Button
                        id="login-submit"
                        type="submit"
                        variant="contained"
                        fullWidth
                        size="large"
                        disabled={loading}
                        startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <LockOutlined />}
                        sx={{
                            py: 1.3,
                            fontSize: '1rem',
                            fontWeight: 700,
                            textTransform: 'none',
                            borderRadius: 2,
                            backgroundColor: '#1565C0',
                            color: '#FFFFFF',
                            '&:hover': { backgroundColor: '#0D47A1' },
                            '&.Mui-disabled': { backgroundColor: '#1565C0', opacity: 0.6, color: '#FFFFFF' },
                        }}
                    >
                        {loading ? 'Signing in...' : 'Sign In'}
                    </Button>
                </Box>

                {/* Forgot password link — flips the card */}
                <Box sx={{ mt: 2, textAlign: 'center' }}>
                    <Link
                        component="button"
                        type="button"
                        onClick={flipToReset}
                        underline="none"
                        sx={{
                            fontSize: '13px',
                            color: 'text.secondary',
                            cursor: 'pointer',
                            transition: 'color 150ms ease',
                            '&:hover': {
                                textDecoration: 'underline',
                                color: isDark ? '#90CAF9' : '#0D47A1',
                            },
                        }}
                    >
                        Forgot your password?
                    </Link>
                </Box>
            </Paper>

            {/* Back face — forgot-password flow */}
            <Paper
                elevation={isDark ? 12 : 8}
                aria-hidden={!flipped}
                sx={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    p: { xs: 3, sm: 5 },
                    borderRadius: '16px',
                    textAlign: 'left',
                    backgroundColor: isDark ? 'rgba(20,30,50,0.92)' : 'rgba(255,255,255,0.98)',
                    backdropFilter: 'blur(8px)',
                    border: isDark ? '1px solid rgba(255,255,255,0.06)' : '1px solid rgba(13,71,161,0.06)',
                    boxShadow: isDark
                        ? '0 20px 60px rgba(0,0,0,0.45), 0 2px 8px rgba(0,0,0,0.3)'
                        : '0 20px 60px rgba(13,71,161,0.12), 0 2px 8px rgba(0,0,0,0.06)',
                    transform: 'rotateY(180deg)',
                    backfaceVisibility: 'hidden',
                    WebkitBackfaceVisibility: 'hidden',
                    pointerEvents: flipped ? 'auto' : 'none',
                }}
            >
                <ForgotPasswordMfaFlow
                    key={resetFlowKey}
                    isDark={isDark}
                    onBackToSignIn={flipToLogin}
                />
            </Paper>
            </Box>
            </Box>
            </Box>

            {/* Copyright footer — 3-line hierarchy, viewport bottom */}
            <Box
                component="footer"
                sx={{
                    position: 'relative',
                    zIndex: 1,
                    width: '100%',
                    textAlign: 'center',
                    px: 2,
                    pb: '20px',
                    mt: 3,
                }}
            >
                {/* Line 1: product attribution */}
                <Typography
                    sx={{
                        fontSize: '11px',
                        letterSpacing: '0.3px',
                        color: footerColor1,
                        lineHeight: 1.5,
                    }}
                >
                    Altitude AI is a product of Revenue Technology Services (RTS)
                </Typography>

                {/* Line 2: copyright */}
                <Typography
                    sx={{
                        fontSize: '10px',
                        letterSpacing: '0.3px',
                        color: footerColor2,
                        mt: '4px',
                        lineHeight: 1.5,
                    }}
                >
                    © {year} Revenue Technology Services. All rights reserved.
                </Typography>

                {/* Line 3: legal links */}
                <Typography
                    sx={{
                        fontSize: '10px',
                        letterSpacing: '0.3px',
                        color: footerColor2,
                        mt: '6px',
                        lineHeight: 1.5,
                    }}
                >
                    <Link
                        href="#"
                        underline="none"
                        sx={{
                            color: 'inherit',
                            '&:hover': { color: footerLinkHover, textDecoration: 'underline' },
                        }}
                    >
                        Privacy Policy
                    </Link>
                    {' · '}
                    <Link
                        href="#"
                        underline="none"
                        sx={{
                            color: 'inherit',
                            '&:hover': { color: footerLinkHover, textDecoration: 'underline' },
                        }}
                    >
                        Terms of Service
                    </Link>
                    {' · '}
                    <Link
                        href="#"
                        underline="none"
                        sx={{
                            color: 'inherit',
                            '&:hover': { color: footerLinkHover, textDecoration: 'underline' },
                        }}
                    >
                        Support
                    </Link>
                </Typography>
            </Box>
        </Box>
    );
}
