import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { BarSeries, TimeChart } from "../components/charts";
import { Card, CardHeader, ErrorNote } from "../components/ui";
import { buildQuery } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { Breakdown } from "../types";

export function AnalyticsPage() {
  const { range } = useRange();
  const { projectId } = useProject();
  const query = useQuery({
    queryKey: ["breakdown", projectId, range],
    enabled: Boolean(projectId),
    queryFn: () => api<Breakdown>(`/api/v1/analytics/breakdown${buildQuery({ range })}`),
  });
  if (query.isLoading) return <p className="text-sm text-zinc-500">Loading analytics…</p>;
  if (query.isError) return <ErrorNote message={query.error.message} />;
  const data = query.data;
  if (!data) return null;
  const severity = Object.entries(data.severity).map(([name, count]) => ({ name, count }));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Log volume" />
        <TimeChart data={data.log_volume} />
      </Card>
      <Card>
        <CardHeader title="Error volume" />
        <TimeChart data={data.error_volume} />
      </Card>
      <Card>
        <CardHeader title="Severity" />
        <BarSeries data={severity} />
      </Card>
      <Card>
        <CardHeader title="Errors by service" />
        <BarSeries data={data.errors_by_service} />
      </Card>
      <Card>
        <CardHeader title="Latency distribution" />
        <BarSeries data={data.latency_buckets} dataKey="count" />
      </Card>
      <Card>
        <CardHeader title="Alert trend" />
        <TimeChart data={data.alert_trend} />
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader title="Top error messages" />
        <ul>
          {data.top_errors.length === 0 && <li className="px-4 py-8 text-sm text-zinc-500">No errors in this window.</li>}
          {data.top_errors.map((item) => (
            <li key={item.message} className="flex justify-between gap-4 border-t border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800">
              <span className="truncate">{item.message}</span>
              <span className="font-mono">{item.count}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader title="Service comparison" />
        <BarSeries data={data.service_comparison.map((item) => ({ name: item.service, count: item.logs }))} />
      </Card>
    </div>
  );
}
