from __future__ import annotations

import logging
from concurrent import futures

from app.db.session import session_scope
from app.services.identity import IdentityService
from app.services.ingestion import IngestionService
from app.telemetry.otlp import _logs_from_proto_request, _metrics_from_proto_request, _spans_from_proto_request

logger = logging.getLogger(__name__)


def _project_from_context(context) -> str:
    import grpc
    from fastapi import HTTPException

    metadata = {key.lower(): value for key, value in context.invocation_metadata()}
    token = metadata.get("authorization") or metadata.get("x-api-key") or ""
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing credentials")
    with session_scope() as db:
        try:
            auth = IdentityService(db).resolve_token(token, None)
            return IdentityService(db).require_ingest(auth)
        except HTTPException as exc:
            if exc.status_code == 429:
                context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Rate limit exceeded")
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")
    context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid credentials")


def start_grpc_server(port: int):
    import grpc
    from opentelemetry.proto.collector.logs.v1 import logs_service_pb2, logs_service_pb2_grpc
    from opentelemetry.proto.collector.metrics.v1 import metrics_service_pb2, metrics_service_pb2_grpc
    from opentelemetry.proto.collector.trace.v1 import trace_service_pb2, trace_service_pb2_grpc

    class Traces(trace_service_pb2_grpc.TraceServiceServicer):
        def Export(self, request, context):
            project_id = _project_from_context(context)
            with session_scope() as db:
                IngestionService(db).ingest_spans(project_id, _spans_from_proto_request(request))
            return trace_service_pb2.ExportTraceServiceResponse()

    class Metrics(metrics_service_pb2_grpc.MetricsServiceServicer):
        def Export(self, request, context):
            project_id = _project_from_context(context)
            with session_scope() as db:
                IngestionService(db).ingest_metrics(project_id, _metrics_from_proto_request(request))
            return metrics_service_pb2.ExportMetricsServiceResponse()

    class Logs(logs_service_pb2_grpc.LogsServiceServicer):
        def Export(self, request, context):
            project_id = _project_from_context(context)
            with session_scope() as db:
                IngestionService(db).ingest_logs(project_id, _logs_from_proto_request(request))
            return logs_service_pb2.ExportLogsServiceResponse()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    trace_service_pb2_grpc.add_TraceServiceServicer_to_server(Traces(), server)
    metrics_service_pb2_grpc.add_MetricsServiceServicer_to_server(Metrics(), server)
    logs_service_pb2_grpc.add_LogsServiceServicer_to_server(Logs(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    logger.info("OTLP gRPC receiver started", extra={"port": port})
    return server
