import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, EmptyState, ErrorNote, Input, SeverityBadge } from "../components/ui";
import { buildQuery, formatMs, formatTime } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { Page, TraceSummary } from "../types";

function windowQuery(range: string) {
  const minutes = { "15m": 15, "1h": 60, "6h": 360, "24h": 1440, "7d": 10080 }[range] ?? 60;
  const end = new Date();
  const start = new Date(end.getTime() - minutes * 60 * 1000);
  return { from: start.toISOString(), to: end.toISOString() };
}

export function TracesPage() {
  const { range } = useRange();
  const { projectId } = useProject();
  const [service, setService] = useState("");
  const query = useQuery({
    queryKey: ["traces", projectId, range, service],
    enabled: Boolean(projectId),
    queryFn: () => api<Page<TraceSummary>>(`/api/v1/traces${buildQuery({ ...windowQuery(range), service, page_size: 50 })}`),
  });
  const items = query.data?.items ?? [];
  return (
    <div className="space-y-3">
      <Input aria-label="Trace service" placeholder="Filter by service" value={service} onChange={(event) => setService(event.target.value)} className="max-w-xs" />
      <Card>
        {query.isLoading && <p className="p-4 text-sm text-zinc-500">Loading traces…</p>}
        {query.isError && <div className="p-4"><ErrorNote message={query.error.message} /></div>}
        {!query.isLoading && items.length === 0 && <EmptyState title="No traces" body="Export OTLP traces to /v1/traces or through the collector." />}
        {items.length > 0 && (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Operation</th>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2">Duration</th>
                <th className="px-3 py-2">Spans</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Start</th>
              </tr>
            </thead>
            <tbody>
              {items.map((trace) => (
                <tr key={trace.trace_id} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="px-3 py-2">
                    <Link className="text-cyan-600" to={`/traces/${trace.trace_id}`}>{trace.root_span_name}</Link>
                  </td>
                  <td className="px-3 py-2">{trace.service}</td>
                  <td className="px-3 py-2 font-mono">{formatMs(trace.duration_ms)}</td>
                  <td className="px-3 py-2">{trace.span_count}</td>
                  <td className="px-3 py-2">{trace.error_count > 0 ? <SeverityBadge severity="ERROR" /> : trace.status}</td>
                  <td className="px-3 py-2 font-mono text-xs">{formatTime(trace.start_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
