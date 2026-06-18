import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useSession } from './context/SessionContext';
import { AuthProvider } from './context/AuthContext';
import { SessionProvider } from './context/SessionContext';
import { ThemeContextProvider } from './context/ThemeContext';
import AuthGuard from './components/common/AuthGuard';
import MainLayout from './components/layout/MainLayout';
import ProtectedRoute from './components/common/ProtectedRoute';
import LoginPage from './pages/login/LoginPage';
import HomePage from './pages/home/HomePage';
import AirlineCpiPage from './pages/airline/AirlineCpiPage';
import CflCpiPage from './pages/cfl/CflCpiPage';
import SftpConnectionsPage from './pages/admin/SftpConnectionsPage';
import IngestionSchedulesPage from './pages/admin/IngestionSchedulesPage';
import IngestionRunsPage from './pages/admin/IngestionRunsPage';
import PasswordManagementPage from './pages/PasswordManagementPage';
import EmailSettingsPage from './pages/admin/settings/EmailSettingsPage';
import IngestionJobsPage from './pages/ingestion/IngestionJobsPage';
import UploadPage from './pages/ingestion/UploadPage';

import SupersetPage from './pages/superset/SupersetPage';
import DashboardViewerPage from './pages/superset/DashboardViewerPage';
import NotAuthorizedPage from './pages/NotAuthorizedPage';
import NotFoundPage from './pages/NotFoundPage';
import ChangePasswordPage from './pages/auth/ChangePasswordPage';
import AcceptInvitePage from './pages/auth/AcceptInvitePage';
import SetupMfaPage from './pages/auth/SetupMfaPage';
import SecurityPage from './pages/auth/SecurityPage';
import { isSuperAdmin } from './utils/access';
import { getPrimaryDashboardId } from './pages/superset/dashboardAccess';

/**
 * RootRoute handles the logic for the base path "/".
 * Admin -> HomePage
 * Single-dashboard tenant -> /dashboards/{their-id}
 * Fallback (no mapping) -> /dashboards listing
 */
function RootRoute() {
  const { session } = useSession();
  if (isSuperAdmin(session)) {
    return <HomePage />;
  }
  const dashboardId = getPrimaryDashboardId(session);
  if (dashboardId) {
    return <Navigate to={`/dashboards/${dashboardId}`} replace />;
  }
  return <Navigate to="/dashboards" replace />;
}

export default function App() {
  return (
    <ThemeContextProvider>
      <AuthProvider>
        <SessionProvider>
          <BrowserRouter>
            <Routes>
              {/* Public route — login page */}
              <Route path="/login" element={<LoginPage />} />

              {/* Public route — accept invite (unauthenticated; invited user sets their own password) */}
              <Route path="/accept-invite" element={<AcceptInvitePage />} />

              {/* Change password — accessible when authenticated, bypasses AuthGuard's password check */}
              <Route path="/change-password" element={
                <AuthGuard>
                  <ChangePasswordPage />
                </AuthGuard>
              } />

              {/* MFA enrollment — reachable when authenticated; the forced
                  gate redirects here (?required=1). Standalone like change-password. */}
              <Route path="/setup-mfa" element={
                <AuthGuard>
                  <SetupMfaPage />
                </AuthGuard>
              } />

              {/* Protected routes — all wrapped in AuthGuard + MainLayout */}
              <Route
                element={
                  <AuthGuard>
                    <MainLayout />
                  </AuthGuard>
                }
              >
                {/* Index page handles landing based on role */}
                <Route path="/" element={<RootRoute />} />

                {/* Security settings (any authenticated user) */}
                <Route path="/security" element={<SecurityPage />} />

                {/* Modules */}
                <Route path="/cpi/airline/jy" element={
                  <ProtectedRoute requiredModules={['airline_jy']} requiredRoles={['TENANT_ADMIN']}>
                    <AirlineCpiPage tenantCode="JY" />
                  </ProtectedRoute>
                } />

                <Route path="/cpi/airline/pw" element={
                  <ProtectedRoute requiredModules={['airline_pw']} requiredRoles={['TENANT_ADMIN']}>
                    <AirlineCpiPage tenantCode="PW" />
                  </ProtectedRoute>
                } />

                <Route path="/cpi/airline/alt" element={
                  <ProtectedRoute requiredModules={['airline_alt']} requiredRoles={['TENANT_ADMIN']}>
                    <AirlineCpiPage tenantCode="ALT" />
                  </ProtectedRoute>
                } />

                <Route path="/cpi/airline/wm" element={
                  <ProtectedRoute requiredModules={['airline_wm']} requiredRoles={['TENANT_ADMIN']}>
                    <AirlineCpiPage tenantCode="WM" />
                  </ProtectedRoute>
                } />

                <Route path="/cpi/cruise/fjl" element={
                  <ProtectedRoute requiredModules={['cfl_fjl']} requiredRoles={['TENANT_ADMIN']}>
                    <CflCpiPage tenantCode="FJL" />
                  </ProtectedRoute>
                } />

                {/* Legacy redirects */}
                <Route path="/airline" element={<Navigate to="/cpi/airline/jy" replace />} />
                <Route path="/cfl" element={<Navigate to="/cpi/cruise/fjl" replace />} />
                {/* Admin (RTS platform admins only) */}
                <Route path="/admin/sftp-connections" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <SftpConnectionsPage />
                  </ProtectedRoute>
                } />
                <Route path="/admin/ingestion-schedules" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <IngestionSchedulesPage />
                  </ProtectedRoute>
                } />
                <Route path="/admin/ingestion-runs" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <IngestionRunsPage />
                  </ProtectedRoute>
                } />
                <Route path="/admin/password-management" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <PasswordManagementPage />
                  </ProtectedRoute>
                } />
                <Route path="/admin/settings/email" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <EmailSettingsPage />
                  </ProtectedRoute>
                } />

                {/* Data Ops (platform admin only) */}
                <Route path="/ingestion" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <IngestionJobsPage />
                  </ProtectedRoute>
                } />
                <Route path="/ingestion/upload" element={
                  <ProtectedRoute requiredRoles={['TENANT_ADMIN']} requireSuperAdmin>
                    <UploadPage />
                  </ProtectedRoute>
                } />

                {/* Analytics Dashboards — tenant-only. Platform admin is
                    redirected home; tenant users still see only the dashboards
                    their enabled_modules permit (see canAccessDashboard). */}
                <Route path="/dashboards" element={
                  <ProtectedRoute denyForSuperAdmin>
                    <SupersetPage />
                  </ProtectedRoute>
                } />
                <Route path="/dashboards/:id" element={
                  <ProtectedRoute denyForSuperAdmin>
                    <DashboardViewerPage />
                  </ProtectedRoute>
                } />

                {/* Status pages */}
                <Route path="/not-authorized" element={<NotAuthorizedPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </SessionProvider>
      </AuthProvider>
    </ThemeContextProvider>
  );
}
