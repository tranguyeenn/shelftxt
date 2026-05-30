import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { UserSettingsProvider } from "@/contexts/UserSettingsContext";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { AddBookPage } from "@/pages/AddBookPage";
import { BookDetailPage } from "@/pages/BookDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { LibraryPage } from "@/pages/LibraryPage";
import { RankingPage } from "@/pages/RankingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { InsightsPage } from "@/pages/InsightsPage";

export function App() {
  return (
    <UserSettingsProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
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
      </BrowserRouter>
    </UserSettingsProvider>
  );
}
