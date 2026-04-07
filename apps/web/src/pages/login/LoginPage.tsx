import React, { useState } from 'react';
import {
    Box,
    Paper,
    TextField,
    Button,
    Typography,
    Alert,
    CircularProgress,
    FormControlLabel,
    Checkbox,
    InputAdornment,
    IconButton,
} from '@mui/material';
import { Visibility, VisibilityOff, LockOutlined } from '@mui/icons-material';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useSession } from '../../context/SessionContext';

export default function LoginPage() {
    const { login, isAuthenticated } = useAuth();
    const { session, isSyncing } = useSession();

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [remember, setRemember] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    // If already logged in, redirect to appropriate landing page
    if (isAuthenticated) {
        // Wait for session to sync with current auth user to prevent landing on wrong user's page
        if (isSyncing) {
            return (
                <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CircularProgress />
                </Box>
            );
        }

        if (session.user.roles.includes('TENANT_ADMIN')) return <Navigate to="/" replace />;
        
        // All other tenant users land on the Dashboards listing page by default
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
        const result = await login(email, password);
        setLoading(false);

        if (!result.success) {
            setError(result.error || 'Login failed');
        }
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
                        id="login-email"
                        label="Email Address"
                        type="email"
                        fullWidth
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="admin@skywave.com"
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
                        sx={{ mb: 1 }}
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

                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5 }}>
                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={remember}
                                    onChange={(e) => setRemember(e.target.checked)}
                                    size="small"
                                    color="primary"
                                />
                            }
                            label={<Typography variant="body2">Remember me</Typography>}
                        />
                    </Box>

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
                        {loading ? 'Signing in…' : 'Sign In'}
                    </Button>
                </Box>

                {/* Footer hint */}
                <Typography variant="caption" color="text.disabled" sx={{ mt: 3, display: 'block' }}>
                    Demo: admin@skywave.com / admin123
                </Typography>
            </Paper>
        </Box>
    );
}
