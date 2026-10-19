import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Button, Card, CardHeader, ErrorNote, Input, JsonBlock } from "../components/ui";
import { copyText, formatTime } from "../lib/utils";
import { useProject } from "../state";
import type { ApiKey, Project } from "../types";

export function ProjectsPage() {
  const client = useQueryClient();
  const { projectId, selectProject } = useProject();
  const [secret, setSecret] = useState<string | null>(null);
  const [error, setError] = useState("");
  const keys = useQuery({
    queryKey: ["keys", projectId],
    enabled: Boolean(projectId),
    queryFn: () => api<ApiKey[]>(`/api/v1/api-keys?project_id=${projectId}`),
  });
  const createProject = useMutation({
    mutationFn: (body: { name: string; slug?: string }) => api<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (project) => {
      selectProject(project.id);
      client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
  const createKey = useMutation({
    mutationFn: (name: string) =>
      api<ApiKey>("/api/v1/api-keys", { method: "POST", body: JSON.stringify({ name, project_id: projectId }) }),
    onSuccess: (key) => {
      setSecret(key.secret ?? null);
      client.invalidateQueries({ queryKey: ["keys"] });
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => api<ApiKey>(`/api/v1/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["keys"] }),
  });
  const testLog = useMutation({
    mutationFn: () => api(`/api/v1/projects/${projectId}/test-log`, { method: "POST" }),
  });
  const endpoint = window.location.origin.replace(":5173", ":8000");
  const snippet = `curl -X POST ${endpoint}/api/v1/logs \\
  -H 'Authorization: Bearer ${secret || "YOUR_PROJECT_API_KEY"}' \\
  -H 'Content-Type: application/json' \\
  -d '{"severity":"ERROR","message":"Payment processing failed","service":"payment-service","environment":"production"}'`;
  const otlp = `exporters:
  otlphttp:
    endpoint: ${endpoint}
    headers:
      authorization: Bearer ${secret || "YOUR_PROJECT_API_KEY"}`;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold">1. Create a project</h2>
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            setError("");
            createProject.mutate(
              { name: String(data.get("name")), slug: String(data.get("slug") || "") || undefined },
              { onError: (err) => setError(err.message) },
            );
          }}
        >
          <Input name="name" required aria-label="Project name" placeholder="Project name" />
          <Input name="slug" aria-label="Project slug" placeholder="slug (optional)" />
          <Button type="submit">Create project</Button>
        </form>
      </Card>
      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold">2. Generate an API key</h2>
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            createKey.mutate(String(data.get("name")), { onError: (err) => setError(err.message) });
          }}
        >
          <Input name="name" required aria-label="Key name" placeholder="Key name" />
          <Button type="submit" disabled={!projectId}>Create</Button>
        </form>
        {secret && (
          <div className="mt-3 rounded-md border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            <p>Copy this key now. It is stored only as a hash.</p>
            <code className="mt-2 block break-all font-mono text-xs">{secret}</code>
            <Button className="mt-2" size="sm" variant="secondary" onClick={() => copyText(secret)}>Copy key</Button>
          </div>
        )}
      </Card>
      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold">3. Send a test event</h2>
        <Button disabled={!projectId} onClick={() => testLog.mutate(undefined, { onError: (err) => setError(err.message) })}>Send test log</Button>
        {testLog.isSuccess && <p className="mt-2 text-sm text-emerald-600">Test log stored. Open Logs to see it.</p>}
      </Card>
      <Card>
        <CardHeader title="API keys" />
        <ul>
          {(keys.data ?? []).map((key) => (
            <li key={key.id} className="flex items-center justify-between border-t border-zinc-200 px-4 py-3 text-sm dark:border-zinc-800">
              <span>
                {key.name}
                <span className="ml-2 font-mono text-xs text-zinc-500">{key.key_prefix}…</span>
                <span className="mt-1 block text-xs text-zinc-500">{key.revoked_at ? `revoked ${formatTime(key.revoked_at)}` : `created ${formatTime(key.created_at)}`}</span>
              </span>
              {!key.revoked_at && <Button size="sm" variant="ghost" onClick={() => revoke.mutate(key.id)}>Revoke</Button>}
            </li>
          ))}
        </ul>
      </Card>
      <Card className="lg:col-span-2">
        <CardHeader title="HTTP and OTLP" action={<Button size="sm" variant="secondary" onClick={() => copyText(snippet)}>Copy curl</Button>} />
        <div className="space-y-3 p-4">
          <JsonBlock value={snippet} />
          <JsonBlock value={otlp} />
          <p className="text-xs text-zinc-500">Any language can POST JSON. OpenTelemetry exporters should target /v1/traces, /v1/metrics, and /v1/logs. The Python SDK is optional.</p>
        </div>
      </Card>
      {error && <ErrorNote message={error} />}
    </div>
  );
}
