import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import { AuthProvider } from "@/contexts/AuthContext";
import { UserSettingsProvider } from "@/contexts/UserSettingsContext";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { AddBookPage } from "@/pages/AddBookPage";
import { BookDetailPage } from "@/pages/BookDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LoginPage } from "@/pages/LoginPage";
import { LibraryPage } from "@/pages/LibraryPage";
import { RankingPage } from "@/pages/RankingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { InsightsPage } from "@/pages/InsightsPage";
import { RegisterPage } from "@/pages/RegisterPage";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <UserSettingsProvider>
          <Routes>
            <Route path="login" element={<LoginPage />} />
            <Route path="register" element={<RegisterPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route index element={<DashboardPage />} />
              <Route path="library" element={<LibraryPage />} />
              <Route path="ranking" element={<RankingPage />} />
              <Route path="book/:id" element={<BookDetailPage />} />
              <Route path="add" element={isReadOnlyDemo ? <Navigate to="/" replace /> : <AddBookPage />} />
              <Route path="insights" element={<InsightsPage />} />
              <Route path="system" element={<Navigate to="/insights" replace />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </UserSettingsProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
