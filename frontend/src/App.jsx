import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { ToastProvider } from './components/ui/Toast'
import ErrorBoundary from './components/ui/ErrorBoundary'
import AppLayout      from './components/layout/AppLayout'
import LandingPage    from './pages/Landing/LandingPage'
import AuthPage       from './pages/Auth/AuthPage'
import VerifyEmail    from './pages/VerifyEmail/VerifyEmail'
import Dashboard      from './pages/Dashboard/Dashboard'
import Upload         from './pages/Upload/Upload'
import Analysis       from './pages/Analysis/Analysis'
import Billing        from './pages/Billing/Billing'
import AdminLayout    from './pages/Admin/AdminLayout'
import AdminDashboard from './pages/Admin/AdminDashboard'
import AdminUsers     from './pages/Admin/AdminUsers'
import AdminDocuments from './pages/Admin/AdminDocuments'
import NotFound       from './pages/NotFound/NotFound'

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="page-loading">Loading…</div>
  return user ? children : <Navigate to="/login" replace />
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/dashboard" replace />
  return children
}

function AppRoutes() {
  return (
    <Routes>
      {/* ── Public landing ── */}
      <Route path="/" element={<LandingPage />} />

      {/* ── Auth ── */}
      <Route path="/login"        element={<AuthPage mode="login" />} />
      <Route path="/register"     element={<AuthPage mode="register" />} />
      <Route path="/verify-email" element={<VerifyEmail />} />

      {/* ── App (authenticated) ── */}
      <Route path="/app" element={<PrivateRoute><AppLayout /></PrivateRoute>}>
        <Route index element={<Navigate to="/app/dashboard" replace />} />
        <Route path="dashboard"     element={<ErrorBoundary><Dashboard /></ErrorBoundary>} />
        <Route path="upload"        element={<ErrorBoundary><Upload /></ErrorBoundary>} />
        <Route path="documents/:id" element={<ErrorBoundary><Analysis /></ErrorBoundary>} />
        <Route path="billing"       element={<ErrorBoundary><Billing /></ErrorBoundary>} />
      </Route>

      {/* ── Legacy redirects — keep old /dashboard links working ── */}
      <Route path="/dashboard"     element={<PrivateRoute><Navigate to="/app/dashboard" replace /></PrivateRoute>} />
      <Route path="/upload"        element={<PrivateRoute><Navigate to="/app/upload" replace /></PrivateRoute>} />
      <Route path="/billing"       element={<PrivateRoute><Navigate to="/app/billing" replace /></PrivateRoute>} />

      {/* ── Admin ── */}
      <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
        <Route index            element={<ErrorBoundary><AdminDashboard /></ErrorBoundary>} />
        <Route path="users"     element={<ErrorBoundary><AdminUsers /></ErrorBoundary>} />
        <Route path="documents" element={<ErrorBoundary><AdminDocuments /></ErrorBoundary>} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </AuthProvider>
  )
}