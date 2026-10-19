import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Button, Card, EmptyState, ErrorNote, Input, JsonBlock, Select, SeverityBadge } from "../components/ui";
import { buildQuery, copyText, formatTime } from "../lib/utils";
import { useProject, useRange } from "../state";
import type { LogRecord, Page } from "../types";

const COLUMNS = ["timestamp", "severity", "service", "environment", "message", "trace"] as const;

function windowQuery(range: string) {
  const end = new Date();
  const start = new Date(end.getTime() - ({ "15m": 15, "1h": 60, "6h": 360, "24h": 1440, "7d": 10080 } as Record<string, number>)[range] * 60 * 1000);
  return { from: start.toISOString(), to: end.toISOString() };
}

export function LogsPage() {
  const { range } = useRange();
  const { projectId } = useProject();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState("");
  const [severity, setSeverity] = useState("");
  const [service, setService] = useState("");
  const [environment, setEnvironment] = useState("");
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>([...COLUMNS]);
  const query = useQuery({
    queryKey: ["logs", projectId, range, q, severity, service, environment, page],
    enabled: Boolean(projectId),
    refetchInterval: refresh || false,
    queryFn: () =>
      api<Page<LogRecord>>(
        `/api/v1/logs${buildQuery({
          ...windowQuery(range),
          q,
          severity,
          service,
          environment,
          page,
          page_size: 50,
        })}`,
      ),
  });
  const items = query.data?.items ?? [];
  return (
    <div className="space-y-3">
      <form
        className="grid gap-2 md:grid-cols-6"
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          setQ(draft);
        }}
      >
        <Input className="md:col-span-2" aria-label="Search logs" placeholder="Search message" value={draft} onChange={(event) => setDraft(event.target.value)} />
        <Select aria-label="Severity" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
          <option value="">All severities</option>
          {["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"].map((level) => (
            <option key={level}>{level}</option>
          ))}
        </Select>
        <Input aria-label="Service" placeholder="Service" value={service} onChange={(event) => { setService(event.target.value); setPage(1); }} />
        <Input aria-label="Environment" placeholder="Environment" value={environment} onChange={(event) => { setEnvironment(event.target.value); setPage(1); }} />
        <div className="flex gap-2">
          <Button type="submit">Search</Button>
          <Select aria-label="Auto refresh" value={String(refresh)} onChange={(event) => setRefresh(Number(event.target.value))}>
            <option value="0">Manual</option>
            <option value="15000">15s</option>
            <option value="30000">30s</option>
          </Select>
        </div>
      </form>
      <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
        {COLUMNS.map((column) => (
          <label key={column} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={columns.includes(column)}
              onChange={() => setColumns((current) => (current.includes(column) ? current.filter((item) => item !== column) : [...current, column]))}
            />
            {column}
          </label>
        ))}
        <Button variant="ghost" size="sm" onClick={() => query.refetch()}>
          Refresh
        </Button>
      </div>
      <Card>
        {query.isLoading && <p className="p-4 text-sm text-zinc-500">Loading logs…</p>}
        {query.isError && <div className="p-4"><ErrorNote message={query.error.message} /></div>}
        {!query.isLoading && items.length === 0 && <EmptyState title="No logs match" body="Send a log with the project API key, or widen the time range." />}
        {items.length > 0 && (
          <div className="overflow-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  {columns.includes("timestamp") && <th className="px-3 py-2">Time</th>}
                  {columns.includes("severity") && <th className="px-3 py-2">Level</th>}
                  {columns.includes("service") && <th className="px-3 py-2">Service</th>}
                  {columns.includes("environment") && <th className="px-3 py-2">Env</th>}
                  {columns.includes("message") && <th className="px-3 py-2">Message</th>}
                  {columns.includes("trace") && <th className="px-3 py-2">Trace</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((log) => (
                  <Fragment key={log.id}>
                    <tr className="cursor-pointer border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900" onClick={() => setOpen(open === log.id ? null : log.id)}>
                      {columns.includes("timestamp") && <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{formatTime(log.timestamp)}</td>}
                      {columns.includes("severity") && <td className="px-3 py-2"><SeverityBadge severity={log.severity} /></td>}
                      {columns.includes("service") && <td className="px-3 py-2">{log.service}</td>}
                      {columns.includes("environment") && <td className="px-3 py-2">{log.environment}</td>}
                      {columns.includes("message") && <td className="max-w-md truncate px-3 py-2">{log.message}</td>}
                      {columns.includes("trace") && (
                        <td className="px-3 py-2 font-mono text-xs" onClick={(event) => event.stopPropagation()}>
                          {log.trace_id ? <Link className="text-cyan-600" to={`/traces/${log.trace_id}`}>{log.trace_id.slice(0, 12)}</Link> : "—"}
                        </td>
                      )}
                    </tr>
                    {open === log.id && (
                      <tr className="border-t border-zinc-200 dark:border-zinc-800">
                        <td colSpan={columns.length} className="space-y-3 px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <Button size="sm" variant="secondary" onClick={() => copyText(log.message)}>Copy message</Button>
                            {log.trace_id && <Button size="sm" variant="secondary" onClick={() => copyText(log.trace_id ?? "")}>Copy trace</Button>}
                            {log.span_id && <Button size="sm" variant="secondary" onClick={() => copyText(log.span_id ?? "")}>Copy span</Button>}
                          </div>
                          {log.exception?.stacktrace && (
                            <pre className="overflow-auto rounded bg-black/80 p-3 font-mono text-xs text-red-100">{log.exception.stacktrace}</pre>
                          )}
                          <JsonBlock value={{ attributes: log.attributes, exception: log.exception, span_id: log.span_id, request_id: log.request_id }} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <div className="flex items-center justify-between text-sm">
        <span className="text-zinc-500">{query.data ? `${query.data.total} logs` : ""}</span>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</Button>
          <Button variant="secondary" size="sm" disabled={!query.data || page * query.data.page_size >= query.data.total} onClick={() => setPage((current) => current + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
