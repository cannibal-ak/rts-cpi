/**
 * Public accept-invite page. Reached via the tokenized link emailed to a newly
 * invited user (/accept-invite?token=...). Unauthenticated — NOT under AuthGuard.
 * Verifies the token, then lets the user set their own password. Mirrors the
 * set-password UX of ForgotPasswordFlow's final step (min 12, confirm, strength).
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Paper, Typography, TextField, Button, Alert, CircularProgress,
  InputAdornment, IconButton,
} from '@mui/material';
import { LockOutlined, CheckCircleOutline, ErrorOutline, Visibility, VisibilityOff } from '@mui/icons-material';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';

const PASSWORD_MIN_LENGTH = 12;
const SPECIAL = /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/;

type Phase = 'verifying' | 'invalid' | 'form' | 'submitting' | 'success';

export default function AcceptInvitePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') || '';

  const [phase, setPhase] = useState<Phase>('verifying');
  const [email, setEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function verify() {
      if (!token) { setPhase('invalid'); return; }
      try {
        const r = await api.auth.verifyInvite(token);
        if (cancelled) return;
        if (r.valid) { setEmail(r.email || ''); setPhase('form'); }
        else setPhase('invalid');
      } catch {
        if (!cancelled) setPhase('invalid');
      }
    }
    verify();
    return () => { cancelled = true; };
  }, [token]);

  const score = useMemo(() => {
    let s = 0;
    if (newPassword.length >= 8) s++;
    if (/[A-Z]/.test(newPassword)) s++;
    if (/\d/.test(newPassword)) s++;
    if (SPECIAL.test(newPassword)) s++;
    return s;
  }, [newPassword]);

  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;
  const meta = !newPassword ? { label: '', color: 'rgba(0,0,0,0.18)' }
    : score <= 1 ? { label: 'Weak', color: '#E53935' }
    : score === 2 ? { label: 'Fair', color: '#FB8C00' }
    : score === 3 ? { label: 'Medium', color: '#FFA000' }
    : { label: 'Strong', color: '#2E7D32' };

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    setError('');
    if (newPassword.length < PASSWORD_MIN_LENGTH) {
      setError(`Password must be at least ${PASSWORD_MIN_LENGTH} characters.`); return;
    }
    if (!/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/\d/.test(newPassword) || !SPECIAL.test(newPassword)) {
      setError('Password must include uppercase, lowercase, a number, and a special character.'); return;
    }
    if (newPassword !== confirmPassword) { setError('Passwords do not match.'); return; }
    setPhase('submitting');
    try {
      const r = await api.auth.acceptInvite({ token, new_password: newPassword });
      if (r.success) {
        setPhase('success');
        window.setTimeout(() => navigate('/login', { replace: true }), 2500);
      } else {
        setError(r.message || 'Could not set your password.'); setPhase('form');
      }
    } catch (err: unknown) {
      const e2 = err as Error & ApiErrorShape;
      setError(e2.message || 'Could not set your password.'); setPhase('form');
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      bgcolor: (t) => t.palette.mode === 'dark' ? '#0A1929' : '#F4F6F8', p: 2 }}>
      <Paper sx={{ p: 4, width: '100%', maxWidth: 440, borderRadius: 2 }}>
        {phase === 'verifying' && (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CircularProgress size={28} />
            <Typography sx={{ mt: 2 }} color="text.secondary">Verifying your invitation…</Typography>
          </Box>
        )}

        {phase === 'invalid' && (
          <Box sx={{ textAlign: 'center' }}>
            <ErrorOutline sx={{ fontSize: 44, color: '#E53935' }} />
            <Typography variant="h6" sx={{ mt: 1, fontWeight: 700 }}>Invitation invalid or expired</Typography>
            <Typography color="text.secondary" sx={{ mt: 1, mb: 3 }}>
              This invite link is no longer valid. Ask your administrator to send a new invitation.
            </Typography>
            <Button variant="contained" fullWidth onClick={() => navigate('/login')}>Back to sign in</Button>
          </Box>
        )}

        {(phase === 'form' || phase === 'submitting') && (
          <Box component="form" onSubmit={handleSubmit} noValidate>
            <Box sx={{ textAlign: 'center', mb: 2 }}>
              <LockOutlined sx={{ fontSize: 40, color: '#1565C0' }} />
              <Typography variant="h6" sx={{ mt: 1, fontWeight: 700 }}>Set up your account</Typography>
              <Typography color="text.secondary" sx={{ mt: 0.5 }}>
                {email ? <>Choose a password for <strong>{email}</strong></> : 'Choose your password'}
              </Typography>
            </Box>

            {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Must be at least {PASSWORD_MIN_LENGTH} characters with uppercase, lowercase, number, and special character.
            </Typography>

            <TextField label="New password" type={showPassword ? 'text' : 'password'} fullWidth autoFocus
              value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password"
              sx={{ mb: 1 }}
              InputProps={{ endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowPassword(s => !s)} edge="end" size="small" aria-label="Toggle password visibility">
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ) }}
            />

            <Box sx={{ mb: 1.5 }}>
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                {[0, 1, 2, 3].map((i) => (
                  <Box key={i} sx={{ flex: 1, height: 4, borderRadius: 2,
                    backgroundColor: newPassword.length > 0 && i < score ? meta.color
                      : (t) => t.palette.mode === 'dark' ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.08)' }} />
                ))}
              </Box>
              {meta.label && (
                <Typography sx={{ fontSize: 11, mt: 0.5, color: meta.color, fontWeight: 600, letterSpacing: '0.05em' }}>
                  {meta.label}
                </Typography>
              )}
            </Box>

            <TextField label="Confirm password" type={showPassword ? 'text' : 'password'} fullWidth
              value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} autoComplete="new-password"
              error={confirmPassword.length > 0 && !passwordsMatch}
              helperText={confirmPassword.length > 0 && !passwordsMatch ? 'Passwords do not match' : ' '}
            />

            <Button type="submit" variant="contained" fullWidth size="large" disabled={phase === 'submitting'}
              startIcon={phase === 'submitting' ? <CircularProgress size={18} color="inherit" /> : null} sx={{ mt: 1 }}>
              {phase === 'submitting' ? 'Setting password…' : 'Set password & continue'}
            </Button>
          </Box>
        )}

        {phase === 'success' && (
          <Box sx={{ textAlign: 'center' }}>
            <CheckCircleOutline sx={{ fontSize: 44, color: '#2E7D32' }} />
            <Typography variant="h6" sx={{ mt: 1, fontWeight: 700 }}>Account ready</Typography>
            <Typography color="text.secondary" sx={{ mt: 1, mb: 3 }}>
              Your password has been set. Redirecting you to sign in…
            </Typography>
            <Button variant="contained" fullWidth onClick={() => navigate('/login', { replace: true })}>Go to sign in</Button>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
