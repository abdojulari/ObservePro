import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { Card, CardHeader, EmptyState, ErrorNote, JsonBlock, SeverityBadge } from "../components/ui";
import { formatMs, formatTime } from "../lib/utils";
import { useProject } from "../state";
import type { SpanRecord, TraceDetail } from "../types";

function depthOf(span: SpanRecord, byId: Map<string, SpanRecord>) {
  let depth = 0;
  let parent = span.parent_span_id;
  const seen = new Set<string>();
  while (parent && byId.has(parent) && !seen.has(parent) && depth < 32) {
    seen.add(parent);
    depth += 1;
    parent = byId.get(parent)?.parent_span_id;
  }
  return depth;
}

export function TraceDetailPage() {
  const { traceId = "" } = useParams();
  const { projectId } = useProject();
  const [selected, setSelected] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["trace", projectId, traceId],
    enabled: Boolean(projectId && traceId),
    queryFn: () => api<TraceDetail>(`/api/v1/traces/${traceId}`),
  });
  const spans = query.data?.spans ?? [];
  const byId = useMemo(() => new Map(spans.map((span) => [span.span_id, span])), [spans]);
  const start = spans.reduce((min, span) => Math.min(min, new Date(span.start_time).getTime()), Number.POSITIVE_INFINITY);
  const end = spans.reduce((max, span) => Math.max(max, new Date(span.end_time).getTime()), 0);
  const width = Math.max(1, end - start);
  const active = spans.find((span) => span.span_id === selected) ?? spans[0];
  if (query.isLoading) return <p className="text-sm text-zinc-500">Loading trace…</p>;
  if (query.isError) return <ErrorNote message={query.error.message} />;
  if (!query.data) return null;
  return (
    <div className="space-y-4">
      <div>
        <Link className="text-xs text-cyan-600" to="/traces">Back to traces</Link>
        <h1 className="mt-1 font-mono text-lg">{query.data.root_span_name}</h1>
        <p className="text-sm text-zinc-500">{query.data.service} · {formatMs(query.data.duration_ms)} · {query.data.span_count} spans</p>
      </div>
      <Card>
        <CardHeader title="Waterfall" />
        {spans.length === 0 ? <EmptyState title="No spans" body="This trace has no stored spans." /> : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {spans.map((span) => {
              const offset = ((new Date(span.start_time).getTime() - start) / width) * 100;
              const bar = Math.max(1.5, (span.duration_ms / width) * 100);
              return (
                <li key={span.span_id}>
                  <button type="button" className="grid w-full grid-cols-[minmax(180px,280px)_1fr_80px] items-center gap-3 px-4 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-900" style={{ paddingLeft: 16 + depthOf(span, byId) * 16 }} onClick={() => setSelected(span.span_id)}>
                    <span className="truncate">{span.name}</span>
                    <span className="relative h-2 rounded bg-zinc-200 dark:bg-zinc-800">
                      <span className={`absolute top-0 h-2 rounded ${span.status_code === "error" ? "bg-red-600" : "bg-cyan-500"}`} style={{ left: `${offset}%`, width: `${bar}%` }} />
                    </span>
                    <span className="font-mono text-xs">{formatMs(span.duration_ms)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
      {active && (
        <Card>
          <CardHeader title={active.name} />
          <div className="space-y-3 px-4 py-3 text-sm">
            <p className="flex flex-wrap gap-2">
              <SeverityBadge severity={active.status_code === "error" ? "ERROR" : "INFO"} />
              <span>{active.service}</span>
              <span className="font-mono text-xs text-zinc-500">{active.kind}</span>
              <span className="font-mono text-xs">{formatTime(active.start_time)}</span>
            </p>
            {active.status_message && <p>{active.status_message}</p>}
            <JsonBlock value={{ attributes: active.attributes, events: active.events, resource: active.resource_attributes, links: active.links }} />
          </div>
        </Card>
      )}
      <Card>
        <CardHeader title="Related logs" />
        {query.data.logs.length === 0 ? <EmptyState title="No correlated logs" body="Logs that carry this trace ID appear here." /> : (
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {query.data.logs.map((log) => (
              <li key={log.id} className="px-4 py-3 text-sm">
                <SeverityBadge severity={log.severity} /> <span className="ml-2">{log.message}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
