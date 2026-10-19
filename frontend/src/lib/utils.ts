import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const RANGES = [
  { id: "15m", label: "15m" },
  { id: "1h", label: "1h" },
  { id: "6h", label: "6h" },
  { id: "24h", label: "24h" },
  { id: "7d", label: "7d" },
] as const;

export type RangeId = (typeof RANGES)[number]["id"];

const RANGE_MS: Record<RangeId, number> = {
  "15m": 15 * 60 * 1000,
  "1h": 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
};

export function rangeDurationMs(range: RangeId) {
  return RANGE_MS[range];
}

export function formatTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { hour12: false });
}

export function formatNumber(value?: number | null, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

export function formatRate(value?: number | null) {
  if (value === null || value === undefined) return "—";
  if (value >= 1) return `${formatNumber(value, 2)}/s`;
  return `${formatNumber(value * 60, 2)}/min`;
}

export function formatMs(value?: number | null) {
  if (value === null || value === undefined) return "—";
  if (value >= 1000) return `${formatNumber(value / 1000, 2)}s`;
  return `${formatNumber(value, 1)}ms`;
}

export function buildQuery(params: Record<string, string | number | boolean | null | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function severityClass(severity: string) {
  switch (severity.toUpperCase()) {
    case "TRACE":
    case "DEBUG":
      return "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
    case "INFO":
    case "LOW":
      return "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300";
    case "WARN":
    case "WARNING":
    case "MEDIUM":
      return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
    case "ERROR":
    case "HIGH":
      return "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
    case "FATAL":
    case "CRITICAL":
    case "EMERGENCY":
      return "bg-red-700 text-white dark:bg-red-700 dark:text-white";
    default:
      return "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  }
}

export async function copyText(value: string) {
  await navigator.clipboard.writeText(value);
}
