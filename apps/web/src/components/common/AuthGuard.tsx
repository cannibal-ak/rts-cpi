import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress, Typography } from '@mui/material';
import { useAuth } from '../../context/AuthContext';
import { useSession } from '../../context/SessionContext';

/**
 * AuthGuard wraps all protected routes.
 * - While checking auth state it shows a loading spinner.
 * - If not authenticated it redirects to /login, preserving the intended URL.
 */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
    const { isAuthenticated, isLoading } = useAuth();
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
        // Save the path user was trying to visit so we can redirect after login
        return <Navigate to="/login" state={{ from: location.pathname }} replace />;
    }

    return <>{children}</>;
}
