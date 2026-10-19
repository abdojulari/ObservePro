"""Fail-open client for the ObservePro HTTP API and OpenTelemetry traces."""

from observability_client.client import BufferFull, ObservabilityClient
from observability_client.handler import ObservabilityHandler

__all__ = ["BufferFull", "ObservabilityClient", "ObservabilityHandler"]
