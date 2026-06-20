import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './context/AuthContext';
import MainLayout from './components/layout/MainLayout';
import WaterEffect from './components/ui/WaterEffect';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import IODBValidator from './components/modules/IODBValidator';
import DataSheetGenerator from './components/modules/DataSheetGenerator';
import CoverSheetGenerator from './components/modules/CoverSheetGenerator';
import InstrumentListGenerator from './components/modules/InstrumentListGenerator';
import IOListGenerator from './components/modules/IOListGenerator';
import CableScheduleGenerator from './components/modules/CableScheduleGenerator';
import LoopWiringGenerator from './components/modules/LoopWiringGenerator';
import SmartDatasheetExtractor from './components/modules/SmartDatasheetExtractor';
import AdminManagement from './components/modules/AdminManagement';
import ErrorBoundary from './components/ui/ErrorBoundary';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Protected Route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

// Public Route wrapper (redirect to dashboard if already logged in)
function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <LoginPage />
          </PublicRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicRoute>
            <RegisterPage />
          </PublicRoute>
        }
      />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="validator" element={<IODBValidator />} />
        <Route path="instrument-list" element={<InstrumentListGenerator />} />
        <Route path="io-list" element={<IOListGenerator />} />
        <Route path="datasheet" element={<DataSheetGenerator />} />
        <Route path="cover-sheet" element={<CoverSheetGenerator />} />
        <Route path="cable-schedule" element={<CableScheduleGenerator />} />
        <Route path="loop-wiring" element={<LoopWiringGenerator />} />
        <Route path="smart-datasheet" element={<SmartDatasheetExtractor />} />
        <Route path="admin" element={<AdminManagement />} />
      </Route>

      {/* Catch all - redirect to home */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <WaterEffect />
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
