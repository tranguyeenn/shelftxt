import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { AuthProvider } from "@/contexts/AuthContext";
import { UserSettingsProvider } from "@/contexts/UserSettingsContext";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { AddBookPage } from "@/pages/AddBookPage";
import { BookDetailPage } from "@/pages/BookDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { LibraryPage } from "@/pages/LibraryPage";
import { RankingPage } from "@/pages/RankingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { InsightsPage } from "@/pages/InsightsPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { RegisterPage } from "@/pages/RegisterPage";

function LegacyBookRedirect() {
  const { id } = useParams();
  return <Navigate to={`/app/book/${encodeURIComponent(id ?? "")}`} replace />;
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <UserSettingsProvider>
          <Routes>
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
            <Route index element={<LandingPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route path="app">
                <Route index element={<DashboardPage />} />
                <Route path="home" element={<Navigate to="/app" replace />} />
                <Route path="library" element={<LibraryPage />} />
                <Route path="discover" element={<RankingPage />} />
                <Route path="ranking" element={<Navigate to="/app/discover" replace />} />
                <Route path="book/:id" element={<BookDetailPage />} />
                <Route path="add" element={isReadOnlyDemo ? <Navigate to="/app" replace /> : <AddBookPage />} />
                <Route path="insights" element={<InsightsPage />} />
                <Route path="profile" element={<ProfilePage />} />
                <Route path="system" element={<Navigate to="/app/insights" replace />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="*" element={<Navigate to="/app" replace />} />
              </Route>
              <Route path="library" element={<Navigate to="/app/library" replace />} />
              <Route path="discover" element={<Navigate to="/app/discover" replace />} />
              <Route path="ranking" element={<Navigate to="/app/discover" replace />} />
              <Route path="book/:id" element={<LegacyBookRedirect />} />
              <Route path="add" element={<Navigate to="/app/add" replace />} />
              <Route path="insights" element={<Navigate to="/app/insights" replace />} />
              <Route path="profile" element={<Navigate to="/app/profile" replace />} />
              <Route path="system" element={<Navigate to="/app/insights" replace />} />
              <Route path="settings" element={<Navigate to="/app/settings" replace />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </UserSettingsProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
