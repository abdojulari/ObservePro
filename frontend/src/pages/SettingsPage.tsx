import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, ErrorNote } from "../components/ui";
import { useTheme } from "../state";
import type { PlatformInfo } from "../types";

export function SettingsPage() {
  const { theme, toggle } = useTheme();
  const query = useQuery({
    queryKey: ["platform"],
    queryFn: () => api<PlatformInfo>("/api/v1/platform"),
  });
  if (query.isLoading) return <p className="text-sm text-zinc-500">Loading settings…</p>;
  if (query.isError) return <ErrorNote message={query.error.message} />;
  const info = query.data;
  if (!info) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="space-y-2 p-4 text-sm">
        <h2 className="font-semibold">Platform</h2>
        <p>Version {info.version} · {info.environment}</p>
        <p>Storage {info.storage} · database {info.database} · redis {info.redis}</p>
        <p>Retention {info.retention_days} days · rate limit {info.rate_limit_per_minute}/min · max body {info.max_body_bytes} bytes</p>
        <p>Ingestion {info.ingestion_semantics} · OTLP gRPC {info.otlp_grpc_enabled ? "enabled" : "disabled"}</p>
        <button type="button" className="text-cyan-600" onClick={toggle}>Theme: {theme}</button>
      </Card>
      <Card className="p-4 text-sm">
        <h2 className="mb-2 font-semibold">Limits</h2>
        <ul className="list-disc space-y-2 pl-4 text-zinc-600 dark:text-zinc-300">
          {info.limitations.map((item) => <li key={item}>{item}</li>)}
        </ul>
        <p className="mt-3 text-xs text-zinc-500">Telemetry can contain personal or confidential data. Restrict dashboard access and keep retention short.</p>
      </Card>
    </div>
  );
}
