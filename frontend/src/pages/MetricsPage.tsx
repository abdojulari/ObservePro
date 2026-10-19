import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { TimeChart } from "../components/charts";
import { Card, CardHeader, EmptyState, ErrorNote, Select } from "../components/ui";
import { buildQuery, formatNumber } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { MetricName, MetricSummary, Timeseries } from "../types";

export function MetricsPage() {
  const { range } = useRange();
  const { projectId } = useProject();
  const [name, setName] = useState("");
  const names = useQuery({
    queryKey: ["metric-names", projectId],
    enabled: Boolean(projectId),
    queryFn: () => api<MetricName[]>("/api/v1/metrics/names"),
  });
  const selected = name || names.data?.[0]?.name || "";
  const summary = useQuery({
    queryKey: ["metric-summary", projectId, selected, range],
    enabled: Boolean(projectId && selected),
    queryFn: () => api<MetricSummary>(`/api/v1/metrics/summary${buildQuery({ name: selected, range })}`),
  });
  const series = useQuery({
    queryKey: ["metric-series", projectId, selected, range],
    enabled: Boolean(projectId && selected),
    queryFn: () => api<Timeseries>(`/api/v1/metrics/timeseries${buildQuery({ name: selected, range })}`),
  });
  if (names.isError) return <ErrorNote message={names.error.message} />;
  if (!names.isLoading && (names.data?.length ?? 0) === 0) {
    return <EmptyState title="No metrics" body="Send OTLP metrics or POST /api/v1/metrics. Histogram buckets are preserved for percentiles." />;
  }
  const stats = summary.data;
  return (
    <div className="space-y-4">
      <Select aria-label="Metric" value={selected} onChange={(event) => setName(event.target.value)} className="max-w-md">
        {(names.data ?? []).map((metric) => (
          <option key={metric.name} value={metric.name}>{metric.name} ({metric.type})</option>
        ))}
      </Select>
      {summary.isError && <ErrorNote message={summary.error.message} />}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ["Samples", stats?.sample_count],
          ["Count", stats?.count],
          ["Avg", stats?.avg],
          ["P50", stats?.p50],
          ["P95", stats?.p95],
          ["P99", stats?.p99],
          ["Min", stats?.min],
          ["Max", stats?.max],
        ].map(([label, value]) => (
          <Card key={String(label)} className="px-4 py-3">
            <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
            <p className="mt-1 font-mono text-xl">{formatNumber(typeof value === "number" ? value : null, 2)}</p>
          </Card>
        ))}
      </div>
      {stats?.approximate && <p className="text-xs text-amber-600">This histogram was merged from unequal bucket layouts, so percentiles are approximate.</p>}
      <Card>
        <CardHeader title={selected || "Series"} />
        <TimeChart data={(series.data?.points ?? []).map((point) => ({ timestamp: point.timestamp, count: point.p95 ?? point.avg ?? point.value ?? point.count ?? 0 }))} />
      </Card>
    </div>
  );
}
