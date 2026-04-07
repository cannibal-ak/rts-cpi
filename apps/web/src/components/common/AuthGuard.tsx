import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useAuth } from '../../context/AuthContext';
import { useSession } from '../../context/SessionContext';

/**
 * AuthGuard wraps all protected routes.
 * - While checking auth state it shows a loading spinner.
 * - If not authenticated it redirects to /login, preserving the intended URL.
 * - If must_change_password is true, redirects to /change-password.
 */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
    const { isAuthenticated, isLoading, mustChangePassword } = useAuth();
    const { isSyncing } = useSession();
    const location = useLocation();

    if (isLoading || (isAuthenticated && isSyncing)) {
        return (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', gap: 2 }}>
                <CircularProgress />
                <Typography variant="body2" color="text.secondary">
                    {isLoading ? 'Checking authentication...' : 'Synchronizing session...'}
                </Typography>
            </Box>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location.pathname }} replace />;
    }

    // Forced password change — only allow /change-password
    if (mustChangePassword && location.pathname !== '/change-password') {
        return <Navigate to="/change-password" replace />;
    }

    return <>{children}</>;
}
