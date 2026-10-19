import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, EmptyState, ErrorNote, StatusDot } from "../components/ui";
import { buildQuery, formatTime } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { ServiceInfo } from "../types";

export function ServicesPage() {
  const { range } = useRange();
  const { projectId } = useProject();
  const query = useQuery({
    queryKey: ["services", projectId, range],
    enabled: Boolean(projectId),
    queryFn: () => api<ServiceInfo[]>(`/api/v1/services${buildQuery({ range })}`),
  });
  if (query.isLoading) return <p className="text-sm text-zinc-500">Loading services…</p>;
  if (query.isError) return <ErrorNote message={query.error.message} />;
  const items = query.data ?? [];
  return (
    <Card>
      {items.length === 0 && <EmptyState title="No services discovered" body="A service is recorded the first time it sends logs, spans, metrics, or events." />}
      {items.length > 0 && (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2">Service</th>
              <th className="px-3 py-2">Environment</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2">Health</th>
              <th className="px-3 py-2">Logs</th>
              <th className="px-3 py-2">Errors</th>
              <th className="px-3 py-2">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {items.map((service) => (
              <tr key={`${service.name}-${service.environment}`} className="border-t border-zinc-200 dark:border-zinc-800">
                <td className="px-3 py-2">{service.name}</td>
                <td className="px-3 py-2">{service.environment}</td>
                <td className="px-3 py-2 font-mono text-xs">{service.version || "—"}</td>
                <td className="px-3 py-2"><StatusDot health={service.health} /></td>
                <td className="px-3 py-2">{service.log_count}</td>
                <td className="px-3 py-2">{service.error_count}</td>
                <td className="px-3 py-2 font-mono text-xs">{formatTime(service.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
