import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

interface Point {
  timestamp?: string;
  count?: number;
  value?: number | null;
  p95?: number | null;
  label?: string;
  name?: string;
  bucket?: string;
  logs?: number;
  errors?: number;
  service?: string;
}

function labelOf(point: Point) {
  if (point.bucket) return point.bucket;
  if (point.service) return point.service;
  if (point.name) return point.name;
  if (point.timestamp) return point.timestamp.slice(5, 16).replace("T", " ");
  return "";
}

export function TimeChart({ data, dataKey = "count" }: { data: Point[]; dataKey?: string }) {
  const rows = data.map((point) => ({ ...point, label: labelOf(point), plot: Number(point[dataKey as keyof Point] ?? 0) }));
  if (!rows.length) return <p className="px-4 py-10 text-center text-sm text-zinc-500">No telemetry in this window.</p>;
  return (
    <div className="h-56 w-full px-2 py-3">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.12} />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={24} />
          <YAxis tick={{ fontSize: 11 }} width={42} />
          <Tooltip />
          <Area type="monotone" dataKey="plot" name={dataKey} stroke="#0891b2" fill="#0891b233" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BarSeries({ data, dataKey = "count", category = "label" }: { data: Point[]; dataKey?: string; category?: string }) {
  const rows = data.map((point) => ({ ...point, label: labelOf(point) }));
  if (!rows.length) return <p className="px-4 py-10 text-center text-sm text-zinc-500">No telemetry in this window.</p>;
  return (
    <div className="h-56 w-full px-2 py-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.12} />
          <XAxis dataKey={category === "label" ? "label" : category} tick={{ fontSize: 11 }} minTickGap={16} />
          <YAxis tick={{ fontSize: 11 }} width={42} />
          <Tooltip />
          <Bar dataKey={dataKey} fill="#0e7490" radius={3} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
