import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes } from "../App";
import { setProjectId, setToken } from "../api/client";
import { AuthProvider, ProjectProvider, RangeProvider } from "../state";

export function renderAt(path: string, options?: RenderOptions) {
  setToken("test-token");
  setProjectId("project-1");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RangeProvider>
          <ProjectProvider>
            <MemoryRouter initialEntries={[path]}>
              <AppRoutes />
            </MemoryRouter>
          </ProjectProvider>
        </RangeProvider>
      </AuthProvider>
    </QueryClientProvider>,
    options,
  );
}

const overview = {
  logs: { total: 12, error: 3, fatal: 1, timeseries: [{ timestamp: "2026-10-19T12:00:00Z", count: 4 }] },
  alerts: { active: 2, firing: 1, acknowledged: 1, resolved: 0 },
  traffic: { request_count: 20, request_rate: 0.1, error_rate: 5, p50_ms: 10, p95_ms: 40, p99_ms: 80, has_data: true, latency_approximate: false },
  ingestion: { logs: 12, spans: 4, metrics: 2, events_per_second: 0.05 },
  services: [{ name: "payments", environment: "dev", version: "1", first_seen: "2026-10-19T12:00:00Z", last_seen: "2026-10-19T12:00:00Z", health: "healthy", log_count: 12, error_count: 3, span_count: 4 }],
  recent_errors: [],
  recent_alerts: [],
};

export function installApi() {
  const calls: { path: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";
      calls.push({ path, method });
      const url = path.split("?")[0];
      let body: unknown = {};
      if (url.endsWith("/projects")) body = [{ id: "project-1", name: "Payments", slug: "payments", created_at: "2026-10-19T12:00:00Z" }, { id: "project-2", name: "Billing", slug: "billing", created_at: "2026-10-19T12:00:00Z" }];
      else if (url.endsWith("/analytics/overview") || url.endsWith("/analytics/breakdown")) {
        body = url.endsWith("/breakdown")
          ? { log_volume: [], error_volume: [], severity: { ERROR: 3 }, errors_by_service: [], active_services: [], top_errors: [], alert_trend: [], latency_buckets: [], service_comparison: [] }
          : overview;
      } else if (url.endsWith("/logs")) {
        body = {
          items: [{ id: "log-1", project_id: "project-1", timestamp: "2026-10-19T12:00:00Z", ingested_at: "2026-10-19T12:00:00Z", severity: "ERROR", severity_number: 17, message: "Payment processing failed", service: "payments", environment: "dev", attributes: { order_id: "order-123" }, trace_id: "abc123", span_id: "span1" }],
          total: 1,
          page: 1,
          page_size: 50,
        };
      } else if (url.includes("/traces/abc123")) {
        body = { trace_id: "abc123", root_span_name: "POST /pay", service: "payments", start_time: "2026-10-19T12:00:00Z", end_time: "2026-10-19T12:00:01Z", duration_ms: 40, span_count: 1, error_count: 0, status: "ok", spans: [{ id: "s", trace_id: "abc123", span_id: "span1", name: "POST /pay", kind: "server", start_time: "2026-10-19T12:00:00Z", end_time: "2026-10-19T12:00:01Z", duration_ms: 40, status_code: "ok", service: "payments", attributes: {}, events: [], links: [], resource_attributes: {} }], logs: [] };
      } else if (url.endsWith("/alerts") && method === "GET") {
        body = { items: [{ id: "alert-1", fingerprint: "fp", title: "Payment failure rate", message: "above threshold", severity: "CRITICAL", status: "FIRING", service: "payments", first_seen: "2026-10-19T12:00:00Z", last_seen: "2026-10-19T12:01:00Z", history: [] }], total: 1, page: 1, page_size: 50 };
      } else if (url.endsWith("/alerts/alert-1") && method === "GET") {
        body = { id: "alert-1", fingerprint: "fp", title: "Payment failure rate", message: "above threshold", severity: "CRITICAL", status: "FIRING", service: "payments", first_seen: "2026-10-19T12:00:00Z", last_seen: "2026-10-19T12:01:00Z", history: [{ id: "h1", to_status: "FIRING", message: "opened", created_at: "2026-10-19T12:00:00Z" }] };
      } else if (url.endsWith("/acknowledge")) {
        body = { id: "alert-1", fingerprint: "fp", title: "Payment failure rate", message: "above threshold", severity: "CRITICAL", status: "ACKNOWLEDGED", first_seen: "2026-10-19T12:00:00Z", last_seen: "2026-10-19T12:01:00Z", history: [] };
      } else if (url.endsWith("/alert-rules") || url.endsWith("/notification-channels")) body = [];
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}
