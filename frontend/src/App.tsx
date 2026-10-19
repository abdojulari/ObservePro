import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { AlertsPage } from "./pages/AlertsPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { LoginPage } from "./pages/LoginPage";
import { LogsPage } from "./pages/LogsPage";
import { MetricsPage } from "./pages/MetricsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ServicesPage } from "./pages/ServicesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TraceDetailPage } from "./pages/TraceDetailPage";
import { TracesPage } from "./pages/TracesPage";
import { AuthProvider, ProjectProvider, RangeProvider, useAuth } from "./state";

function Guard({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <Guard>
            <AppLayout />
          </Guard>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="traces" element={<TracesPage />} />
        <Route path="traces/:traceId" element={<TraceDetailPage />} />
        <Route path="metrics" element={<MetricsPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RangeProvider>
          <ProjectProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </ProjectProvider>
        </RangeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
