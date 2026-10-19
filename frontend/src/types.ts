export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExceptionInfo {
  type?: string | null;
  message?: string | null;
  stacktrace?: string | null;
}

export interface LogRecord {
  id: string;
  project_id: string;
  timestamp: string;
  ingested_at: string;
  severity: string;
  severity_number: number;
  message: string;
  service: string;
  environment: string;
  logger?: string | null;
  trace_id?: string | null;
  span_id?: string | null;
  request_id?: string | null;
  hostname?: string | null;
  version?: string | null;
  source_file?: string | null;
  source_line?: number | null;
  attributes: Record<string, unknown>;
  exception?: ExceptionInfo | null;
  event_id?: string | null;
}

export interface TraceSummary {
  trace_id: string;
  root_span_name: string;
  service: string;
  environment?: string | null;
  start_time: string;
  end_time: string;
  duration_ms: number;
  span_count: number;
  error_count: number;
  status: string;
}

export interface SpanRecord {
  id: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  kind: string;
  start_time: string;
  end_time: string;
  duration_ms: number;
  status_code: string;
  status_message?: string | null;
  service: string;
  environment?: string | null;
  attributes: Record<string, unknown>;
  events: unknown[];
  links: unknown[];
  resource_attributes: Record<string, unknown>;
}

export interface TraceDetail extends TraceSummary {
  spans: SpanRecord[];
  logs: LogRecord[];
}

export interface MetricName {
  name: string;
  type: string;
  unit?: string | null;
}

export interface MetricSummary {
  name: string;
  type: string;
  count: number;
  sum?: number | null;
  min?: number | null;
  max?: number | null;
  avg?: number | null;
  rate?: number | null;
  p50?: number | null;
  p95?: number | null;
  p99?: number | null;
  approximate: boolean;
  sample_count: number;
}

export interface TimeseriesPoint {
  timestamp: string;
  value?: number | null;
  count?: number | null;
  sum?: number | null;
  avg?: number | null;
  p95?: number | null;
}

export interface Timeseries {
  name: string;
  type: string;
  points: TimeseriesPoint[];
  approximate: boolean;
}

export interface AlertRecord {
  id: string;
  fingerprint: string;
  title: string;
  message: string;
  severity: string;
  status: string;
  service?: string | null;
  environment?: string | null;
  trigger_value?: number | null;
  threshold?: number | null;
  first_seen: string;
  last_seen: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  history: { id: string; from_status?: string | null; to_status: string; message: string; created_at: string }[];
}

export interface AlertRule {
  id: string;
  name: string;
  description?: string | null;
  condition_type: string;
  threshold: number;
  comparison: string;
  window_seconds: number;
  severity: string;
  service?: string | null;
  environment?: string | null;
  metric_name?: string | null;
  event_name?: string | null;
  log_severity?: string | null;
  cooldown_seconds: number;
  auto_resolve: boolean;
  enabled: boolean;
}

export interface Channel {
  id: string;
  name: string;
  channel_type: string;
  url: string;
  enabled: boolean;
}

export interface ServiceInfo {
  name: string;
  environment: string;
  version?: string | null;
  first_seen: string;
  last_seen: string;
  health: string;
  log_count: number;
  error_count: number;
  span_count: number;
}

export interface Project {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  created_at: string;
}

export interface ApiKey {
  id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  revoked_at?: string | null;
  last_used_at?: string | null;
  secret?: string;
}

export interface Overview {
  logs: { total: number; error: number; fatal: number; timeseries: { timestamp: string; count: number }[] };
  alerts: { active: number; firing: number; acknowledged: number; resolved: number };
  traffic: {
    request_count: number;
    request_rate: number;
    error_rate?: number | null;
    p50_ms?: number | null;
    p95_ms?: number | null;
    p99_ms?: number | null;
    has_data: boolean;
    latency_approximate: boolean;
  };
  ingestion: { logs: number; spans: number; metrics: number; events_per_second: number };
  services: ServiceInfo[];
  recent_errors: LogRecord[];
  recent_alerts: { id: string; title: string; severity: string; status: string; service?: string | null; last_seen: string }[];
}

export interface Breakdown {
  log_volume: { timestamp: string; count: number }[];
  error_volume: { timestamp: string; count: number }[];
  severity: Record<string, number>;
  errors_by_service: { name: string; count: number }[];
  active_services: { name: string; count: number }[];
  top_errors: { message: string; count: number }[];
  alert_trend: { timestamp: string; count: number }[];
  latency_buckets: { bucket: string; count: number }[];
  service_comparison: { service: string; logs: number; errors: number }[];
}

export interface PlatformInfo {
  version: string;
  environment: string;
  retention_days: number;
  rate_limit_per_minute: number;
  max_body_bytes: number;
  redis: string;
  database: string;
  storage: string;
  otlp_grpc_enabled: boolean;
  ingestion_semantics: string;
  limitations: string[];
}
