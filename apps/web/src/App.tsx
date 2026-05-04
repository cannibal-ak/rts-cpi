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
import IngestionJobsPage from './pages/ingestion/IngestionJobsPage';
import UploadPage from './pages/ingestion/UploadPage';
import SftpConnectionsPage from './pages/admin/SftpConnectionsPage';
import IngestionSchedulesPage from './pages/admin/IngestionSchedulesPage';
import IngestionRunsPage from './pages/admin/IngestionRunsPage';

import SupersetPage from './pages/superset/SupersetPage';
import DashboardViewerPage from './pages/superset/DashboardViewerPage';
import NotAuthorizedPage from './pages/NotAuthorizedPage';
import NotFoundPage from './pages/NotFoundPage';
import ChangePasswordPage from './pages/auth/ChangePasswordPage';

/**
 * RootRoute handles the logic for the base path "/".
 * Admin -> HomePage
 * Others -> Dashboards
 */
function RootRoute() {
  const { session } = useSession();
  if (session.user.roles.includes('TENANT_ADMIN')) {
    return <HomePage />;
  }
  // All other authenticated users (JY, PW, FJL) land on Dashboards
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

              {/* Change password — accessible when authenticated, bypasses AuthGuard's password check */}
              <Route path="/change-password" element={
                <AuthGuard>
                  <ChangePasswordPage />
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

                <Route path="/cpi/cruise/fjl" element={
                  <ProtectedRoute requiredModules={['cfl_fjl']} requiredRoles={['TENANT_ADMIN']}>
                    <CflCpiPage tenantCode="FJL" />
                  </ProtectedRoute>
                } />

                {/* Legacy redirects */}
                <Route path="/airline" element={<Navigate to="/cpi/airline/jy" replace />} />
                <Route path="/cfl" element={<Navigate to="/cpi/cruise/fjl" replace />} />


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

                {/* Admin (Skywave platform admins only) */}
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

                {/* Analytics Dashboards - Simplified Absolute Paths */}
                <Route path="/dashboards" element={<SupersetPage />} />
                <Route path="/dashboards/:id" element={<DashboardViewerPage />} />

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
