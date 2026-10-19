import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import { api } from "../api/client";
import { Button, Card, EmptyState, ErrorNote, Input, Select, SeverityBadge } from "../components/ui";
import { buildQuery, formatTime } from "../lib/utils";
import { useProject } from "../state";
import type { AlertRecord, AlertRule, Channel, Page } from "../types";

const CONDITIONS = ["error_count", "error_rate", "p95_latency", "metric_threshold", "service_silence", "log_severity", "event_match"];

export function AlertsPage() {
  const { projectId } = useProject();
  const client = useQueryClient();
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const alerts = useQuery({
    queryKey: ["alerts", projectId, status],
    enabled: Boolean(projectId),
    queryFn: () => api<Page<AlertRecord>>(`/api/v1/alerts${buildQuery({ status, page_size: 50 })}`),
  });
  const rules = useQuery({
    queryKey: ["rules", projectId],
    enabled: Boolean(projectId),
    queryFn: () => api<AlertRule[]>("/api/v1/alert-rules"),
  });
  const channels = useQuery({
    queryKey: ["channels", projectId],
    enabled: Boolean(projectId),
    queryFn: () => api<Channel[]>("/api/v1/notification-channels"),
  });
  const detail = useQuery({
    queryKey: ["alert", projectId, selected],
    enabled: Boolean(projectId && selected),
    queryFn: () => api<AlertRecord>(`/api/v1/alerts/${selected}`),
  });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "acknowledge" | "resolve" }) =>
      api<AlertRecord>(`/api/v1/alerts/${id}/${action}`, { method: "POST" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["alert"] });
    },
  });
  const createRule = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<AlertRule>("/api/v1/alert-rules", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["rules"] }),
  });
  const removeRule = useMutation({
    mutationFn: (id: string) => api<void>(`/api/v1/alert-rules/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["rules"] }),
  });
  const createChannel = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Channel>("/api/v1/notification-channels", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["channels"] }),
  });
  const items = alerts.data?.items ?? [];
  return (
    <Tabs.Root defaultValue="incidents">
      <Tabs.List className="mb-4 flex gap-2">
        {["incidents", "rules", "channels"].map((tab) => (
          <Tabs.Trigger key={tab} value={tab} className="rounded-md px-3 py-1.5 text-sm capitalize data-[state=active]:bg-cyan-600 data-[state=active]:text-white">
            {tab}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      <Tabs.Content value="incidents" className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="flex items-center justify-between px-4 py-3">
            <Select aria-label="Alert status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              {["PENDING", "FIRING", "ACKNOWLEDGED", "RESOLVED"].map((item) => <option key={item}>{item}</option>)}
            </Select>
          </div>
          {alerts.isError && <div className="p-4"><ErrorNote message={alerts.error.message} /></div>}
          {items.length === 0 && !alerts.isLoading && <EmptyState title="No alerts" body="Incidents appear when a rule fires or an application posts one." />}
          <ul>
            {items.map((alert) => (
              <li key={alert.id}>
                <button type="button" className="w-full border-t border-zinc-200 px-4 py-3 text-left text-sm dark:border-zinc-800" onClick={() => setSelected(alert.id)}>
                  <span className="flex items-center gap-2">
                    <SeverityBadge severity={alert.severity} />
                    <span className="font-medium">{alert.title}</span>
                  </span>
                  <span className="mt-1 block text-xs text-zinc-500">{alert.status} · {alert.service || "all services"} · {formatTime(alert.last_seen)}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-4 text-sm">
          {!detail.data && <p className="text-zinc-500">Select an incident to see its history.</p>}
          {detail.data && (
            <div className="space-y-3">
              <h2 className="text-base font-semibold">{detail.data.title}</h2>
              <p>{detail.data.message}</p>
              <p className="font-mono text-xs text-zinc-500">fingerprint {detail.data.fingerprint}</p>
              <p>First seen {formatTime(detail.data.first_seen)} · Last seen {formatTime(detail.data.last_seen)}</p>
              <div className="flex gap-2">
                <Button size="sm" disabled={detail.data.status === "RESOLVED"} onClick={() => act.mutate({ id: detail.data!.id, action: "acknowledge" })}>Acknowledge</Button>
                <Button size="sm" variant="secondary" disabled={detail.data.status === "RESOLVED"} onClick={() => act.mutate({ id: detail.data!.id, action: "resolve" })}>Resolve</Button>
              </div>
              {act.isError && <ErrorNote message={act.error.message} />}
              <ul className="space-y-2">
                {detail.data.history.map((item) => (
                  <li key={item.id} className="rounded border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                    <span className="font-mono text-xs">{item.from_status || "—"} → {item.to_status}</span>
                    <p>{item.message}</p>
                    <p className="text-xs text-zinc-500">{formatTime(item.created_at)}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      </Tabs.Content>
      <Tabs.Content value="rules" className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <RuleForm
            onSubmit={(body) => createRule.mutate(body)}
            error={createRule.error instanceof Error ? createRule.error.message : ""}
          />
        </Card>
        <Card>
          {(rules.data ?? []).length === 0 && <EmptyState title="No rules" body="Rules are evaluated by the background worker, not on every ingest." />}
          <ul>
            {(rules.data ?? []).map((rule) => (
              <li key={rule.id} className="flex items-center justify-between border-t border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800">
                <span>
                  <span className="font-medium">{rule.name}</span>
                  <span className="mt-1 block text-xs text-zinc-500">{rule.condition_type} {rule.comparison} {rule.threshold} · {rule.window_seconds}s · cooldown {rule.cooldown_seconds}s</span>
                </span>
                <Button size="sm" variant="ghost" onClick={() => removeRule.mutate(rule.id)}>Delete</Button>
              </li>
            ))}
          </ul>
        </Card>
      </Tabs.Content>
      <Tabs.Content value="channels" className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <ChannelForm onSubmit={(body) => createChannel.mutate(body)} error={createChannel.error instanceof Error ? createChannel.error.message : ""} />
        </Card>
        <Card>
          {(channels.data ?? []).length === 0 && <EmptyState title="No webhooks" body="Without a channel, incidents still move to FIRING. Delivery is optional." />}
          <ul>
            {(channels.data ?? []).map((channel) => (
              <li key={channel.id} className="border-t border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800">
                <p className="font-medium">{channel.name}</p>
                <p className="truncate font-mono text-xs text-zinc-500">{channel.url}</p>
              </li>
            ))}
          </ul>
        </Card>
      </Tabs.Content>
    </Tabs.Root>
  );
}

function RuleForm({ onSubmit, error }: { onSubmit: (body: Record<string, unknown>) => void; error: string }) {
  const [condition, setCondition] = useState("error_count");
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        onSubmit({
          name: data.get("name"),
          condition_type: condition,
          threshold: Number(data.get("threshold") || 0),
          comparison: data.get("comparison"),
          window_seconds: Number(data.get("window") || 300),
          severity: data.get("severity"),
          service: data.get("service") || null,
          metric_name: data.get("metric_name") || null,
          event_name: data.get("event_name") || null,
          log_severity: data.get("log_severity") || null,
          cooldown_seconds: Number(data.get("cooldown") || 300),
          enabled: true,
          auto_resolve: true,
        });
        event.currentTarget.reset();
      }}
    >
      <Input name="name" required placeholder="Rule name" aria-label="Rule name" />
      <Select aria-label="Condition" value={condition} onChange={(event) => setCondition(event.target.value)}>
        {CONDITIONS.map((item) => <option key={item}>{item}</option>)}
      </Select>
      <div className="grid grid-cols-2 gap-2">
        <Select name="comparison" aria-label="Comparison" defaultValue="gt">
          {["gt", "gte", "lt", "lte"].map((item) => <option key={item}>{item}</option>)}
        </Select>
        <Input name="threshold" aria-label="Threshold" type="number" step="any" defaultValue="5" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Input name="window" aria-label="Window seconds" type="number" defaultValue="300" />
        <Input name="cooldown" aria-label="Cooldown seconds" type="number" defaultValue="300" />
      </div>
      <Select name="severity" aria-label="Alert severity" defaultValue="HIGH">
        {["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "EMERGENCY"].map((item) => <option key={item}>{item}</option>)}
      </Select>
      <Input name="service" aria-label="Service filter" placeholder="Service (required for silence)" />
      {condition === "metric_threshold" && <Input name="metric_name" aria-label="Metric name" placeholder="Metric name" required />}
      {condition === "event_match" && <Input name="event_name" aria-label="Event name" placeholder="Event name" required />}
      {condition === "log_severity" && (
        <Select name="log_severity" aria-label="Log severity" defaultValue="ERROR">
          {["ERROR", "FATAL", "WARN", "INFO"].map((item) => <option key={item}>{item}</option>)}
        </Select>
      )}
      {error && <ErrorNote message={error} />}
      <Button type="submit">Create rule</Button>
    </form>
  );
}

function ChannelForm({ onSubmit, error }: { onSubmit: (body: Record<string, unknown>) => void; error: string }) {
  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        onSubmit({ name: data.get("name"), url: data.get("url"), channel_type: "webhook", enabled: true });
        event.currentTarget.reset();
      }}
    >
      <Input name="name" required aria-label="Channel name" placeholder="Channel name" />
      <Input name="url" required aria-label="Webhook URL" placeholder="https://example.com/hooks/observe" />
      {error && <ErrorNote message={error} />}
      <Button type="submit">Add webhook</Button>
    </form>
  );
}
