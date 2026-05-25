import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { AddBookPage } from "@/pages/AddBookPage";
import { BookDetailPage } from "@/pages/BookDetailPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RankingPage } from "@/pages/RankingPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SystemPage } from "@/pages/SystemPage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="ranking" element={<RankingPage />} />
          <Route path="book/:id" element={<BookDetailPage />} />
          <Route path="add" element={<AddBookPage />} />
          <Route path="system" element={<SystemPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
