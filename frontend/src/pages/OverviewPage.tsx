import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { TimeChart } from "../components/charts";
import { Card, CardHeader, EmptyState, ErrorNote, SeverityBadge } from "../components/ui";
import { buildQuery, formatMs, formatNumber, formatRate } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { Overview } from "../types";

export function OverviewPage() {
  const { range } = useRange();
  const { projectId, projects } = useProject();
  const query = useQuery({
    queryKey: ["overview", projectId, range],
    enabled: Boolean(projectId),
    queryFn: () => api<Overview>(`/api/v1/analytics/overview${buildQuery({ range })}`),
  });
  if (!projects.length) {
    return <EmptyState title="Create a project to start" body="Projects isolate telemetry. Generate an API key, send a test log, and it will appear here." />;
  }
  if (query.isLoading) return <p className="text-sm text-zinc-500">Loading overview…</p>;
  if (query.isError) return <ErrorNote message={query.error.message} />;
  const data = query.data;
  if (!data) return null;
  const stats = [
    ["Log volume", formatNumber(data.logs.total)],
    ["Errors", formatNumber(data.logs.error)],
    ["Fatal", formatNumber(data.logs.fatal)],
    ["Active alerts", formatNumber(data.alerts.active)],
    ["Request rate", data.traffic.has_data ? formatRate(data.traffic.request_rate) : "—"],
    ["Error rate", data.traffic.error_rate == null ? "—" : `${formatNumber(data.traffic.error_rate, 2)}%`],
    ["P50", formatMs(data.traffic.p50_ms)],
    ["P95", formatMs(data.traffic.p95_ms)],
    ["P99", formatMs(data.traffic.p99_ms)],
    ["Ingestion", formatRate(data.ingestion.events_per_second)],
  ];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map(([label, value]) => (
          <Card key={label} className="px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
            <p className="mt-1 font-mono text-2xl">{value}</p>
          </Card>
        ))}
      </div>
      {data.traffic.latency_approximate && (
        <p className="text-xs text-amber-600">Latency percentiles are approximate because the sample cap was reached.</p>
      )}
      <Card>
        <CardHeader title="Log volume" />
        <TimeChart data={data.logs.timeseries} />
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Service health" />
          {data.services.length === 0 ? (
            <EmptyState title="No services yet" body="Services appear when logs, spans, or metrics arrive." />
          ) : (
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {data.services.map((service) => (
                <li key={`${service.name}-${service.environment}`} className="flex items-center justify-between px-4 py-3 text-sm">
                  <span>
                    {service.name}
                    <span className="ml-2 font-mono text-xs text-zinc-500">{service.environment}</span>
                  </span>
                  <span className="font-mono text-xs uppercase">{service.health}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Recent errors" />
          {data.recent_errors.length === 0 ? (
            <EmptyState title="No errors in this window" body="Error and fatal logs will show up here." />
          ) : (
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {data.recent_errors.map((log) => (
                <li key={log.id} className="px-4 py-3 text-sm">
                  <div className="mb-1 flex items-center gap-2">
                    <SeverityBadge severity={log.severity} />
                    <span className="text-zinc-500">{log.service}</span>
                  </div>
                  <p className="truncate">{log.message}</p>
                  {log.trace_id && (
                    <Link className="font-mono text-xs text-cyan-600" to={`/traces/${log.trace_id}`}>
                      {log.trace_id}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Card>
        <CardHeader title="Recent alerts" />
        {data.recent_alerts.length === 0 ? (
          <EmptyState title="No active alerts" body="Fired incidents stay here until they are resolved." />
        ) : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {data.recent_alerts.map((alert) => (
              <li key={alert.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <span className="flex items-center gap-2">
                  <SeverityBadge severity={alert.severity} />
                  <Link to="/alerts">{alert.title}</Link>
                </span>
                <span className="font-mono text-xs text-zinc-500">{alert.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
