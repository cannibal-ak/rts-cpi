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
    List,
    ListItem,
    ListItemIcon,
    ListItemText,
} from '@mui/material';
import { Visibility, VisibilityOff, CheckCircle, Cancel, LockReset } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

const MIN_LENGTH = 12;

function checkStrength(pw: string) {
    return {
        length: pw.length >= MIN_LENGTH,
        uppercase: /[A-Z]/.test(pw),
        lowercase: /[a-z]/.test(pw),
        digit: /\d/.test(pw),
        special: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/.test(pw),
    };
}

export default function ChangePasswordPage() {
    const { changePassword, mustChangePassword } = useAuth();
    const navigate = useNavigate();

    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showCurrent, setShowCurrent] = useState(false);
    const [showNew, setShowNew] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);
    const [loading, setLoading] = useState(false);

    const strength = checkStrength(newPassword);
    const allMet = Object.values(strength).every(Boolean);
    const passwordsMatch = newPassword === confirmPassword && confirmPassword.length > 0;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (!currentPassword) { setError('Enter your current password'); return; }
        if (!allMet) { setError('New password does not meet all requirements'); return; }
        if (!passwordsMatch) { setError('Passwords do not match'); return; }

        setLoading(true);
        const result = await changePassword(currentPassword, newPassword);
        setLoading(false);

        if (result.success) {
            setSuccess(true);
            setTimeout(() => navigate('/'), 1500);
        } else {
            setError(result.error || 'Password change failed');
        }
    };

    const rules = [
        { key: 'length', label: `At least ${MIN_LENGTH} characters`, met: strength.length },
        { key: 'uppercase', label: 'One uppercase letter', met: strength.uppercase },
        { key: 'lowercase', label: 'One lowercase letter', met: strength.lowercase },
        { key: 'digit', label: 'One digit', met: strength.digit },
        { key: 'special', label: 'One special character', met: strength.special },
    ];

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
            <Paper elevation={8} sx={{ width: '100%', maxWidth: 480, p: { xs: 3, sm: 5 }, borderRadius: 3 }}>
                <Box sx={{ textAlign: 'center', mb: 3 }}>
                    <LockReset sx={{ fontSize: 48, color: 'primary.main', mb: 1 }} />
                    <Typography variant="h5" fontWeight={700} color="primary.main">
                        Change Password
                    </Typography>
                    {mustChangePassword && (
                        <Alert severity="warning" sx={{ mt: 2, textAlign: 'left' }}>
                            You must change your password before accessing the application.
                        </Alert>
                    )}
                </Box>

                {success ? (
                    <Alert severity="success">Password changed successfully! Redirecting...</Alert>
                ) : (
                    <>
                        {error && (
                            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
                                {error}
                            </Alert>
                        )}

                        <Box component="form" onSubmit={handleSubmit} noValidate>
                            <TextField
                                label="Current Password"
                                type={showCurrent ? 'text' : 'password'}
                                fullWidth
                                value={currentPassword}
                                onChange={(e) => setCurrentPassword(e.target.value)}
                                autoComplete="current-password"
                                sx={{ mb: 2 }}
                                InputProps={{
                                    endAdornment: (
                                        <InputAdornment position="end">
                                            <IconButton onClick={() => setShowCurrent(!showCurrent)} edge="end" size="small">
                                                {showCurrent ? <VisibilityOff /> : <Visibility />}
                                            </IconButton>
                                        </InputAdornment>
                                    ),
                                }}
                            />

                            <TextField
                                label="New Password"
                                type={showNew ? 'text' : 'password'}
                                fullWidth
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                autoComplete="new-password"
                                sx={{ mb: 1 }}
                                InputProps={{
                                    endAdornment: (
                                        <InputAdornment position="end">
                                            <IconButton onClick={() => setShowNew(!showNew)} edge="end" size="small">
                                                {showNew ? <VisibilityOff /> : <Visibility />}
                                            </IconButton>
                                        </InputAdornment>
                                    ),
                                }}
                            />

                            {/* Strength indicators */}
                            <List dense sx={{ mb: 1 }}>
                                {rules.map((r) => (
                                    <ListItem key={r.key} sx={{ py: 0 }}>
                                        <ListItemIcon sx={{ minWidth: 28 }}>
                                            {r.met ? <CheckCircle fontSize="small" color="success" /> : <Cancel fontSize="small" color="disabled" />}
                                        </ListItemIcon>
                                        <ListItemText
                                            primary={r.label}
                                            primaryTypographyProps={{ variant: 'body2', color: r.met ? 'text.primary' : 'text.disabled' }}
                                        />
                                    </ListItem>
                                ))}
                            </List>

                            <TextField
                                label="Confirm New Password"
                                type="password"
                                fullWidth
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                autoComplete="new-password"
                                error={confirmPassword.length > 0 && !passwordsMatch}
                                helperText={confirmPassword.length > 0 && !passwordsMatch ? 'Passwords do not match' : ''}
                                sx={{ mb: 2.5 }}
                            />

                            <Button
                                type="submit"
                                variant="contained"
                                fullWidth
                                size="large"
                                disabled={loading || !allMet || !passwordsMatch}
                                startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <LockReset />}
                                sx={{ py: 1.3, fontSize: '1rem', fontWeight: 700, textTransform: 'none', borderRadius: 2 }}
                            >
                                {loading ? 'Changing...' : 'Change Password'}
                            </Button>
                        </Box>
                    </>
                )}
            </Paper>
        </Box>
    );
}
