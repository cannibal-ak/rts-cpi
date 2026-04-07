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
    MenuItem,
} from '@mui/material';
import { Visibility, VisibilityOff, LockOutlined } from '@mui/icons-material';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useSession } from '../../context/SessionContext';

const TENANT_OPTIONS = [
    { slug: 'jy', label: 'JY Airways' },
    { slug: 'pw', label: 'PW Airlines' },
    { slug: 'fjl', label: 'FJL Cruise' },
    { slug: 'skywave', label: 'Skywave (Admin)' },
];

export default function LoginPage() {
    const { login, isAuthenticated, mustChangePassword } = useAuth();
    const { session, isSyncing } = useSession();
    const navigate = useNavigate();

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [tenantSlug, setTenantSlug] = useState('skywave');
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

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
        const result = await login(email, password, tenantSlug);
        setLoading(false);

        if (!result.success) {
            setError(result.error || 'Login failed');
        }
        // On success, AuthContext updates state → re-render → Navigate triggers above
    };

    return (
        <Box
            sx={{
                minHeight: '100vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: (theme) =>
                    theme.palette.mode === 'light'
                        ? 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)'
                        : 'linear-gradient(135deg, #0f1419 0%, #1a2332 100%)',
                p: 2,
            }}
        >
            <Paper
                elevation={8}
                sx={{
                    width: '100%',
                    maxWidth: 440,
                    p: { xs: 3, sm: 5 },
                    borderRadius: 3,
                    textAlign: 'center',
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
                        sx={{ height: 56, mb: 1.5 }}
                    />
                    <Typography variant="h5" fontWeight={700} color="primary.main">
                        Competitor Pricing Intelligence
                    </Typography>
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
                        id="login-tenant"
                        select
                        label="Tenant"
                        fullWidth
                        value={tenantSlug}
                        onChange={(e) => setTenantSlug(e.target.value)}
                        sx={{ mb: 2 }}
                    >
                        {TENANT_OPTIONS.map((t) => (
                            <MenuItem key={t.slug} value={t.slug}>
                                {t.label}
                            </MenuItem>
                        ))}
                    </TextField>

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
                        sx={{ mb: 2 }}
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
                        sx={{ mb: 2.5 }}
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
                        }}
                    >
                        {loading ? 'Signing in...' : 'Sign In'}
                    </Button>
                </Box>

                {/* Footer */}
                <Typography variant="caption" color="text.disabled" sx={{ mt: 3, display: 'block' }}>
                    Initial passwords are generated by the seed script and must be changed on first login.
                </Typography>
            </Paper>
        </Box>
    );
}
