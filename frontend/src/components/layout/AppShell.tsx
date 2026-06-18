import { Outlet } from "react-router-dom";

import { AppLayout } from "./AppLayout";
import { DemoBanner } from "./DemoBanner";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <AppLayout sidebar={<Sidebar />} banner={<DemoBanner />}>
      <Outlet />
    </AppLayout>
  );
}
