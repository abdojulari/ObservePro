from __future__ import annotations

import ipaddress
import logging
import socket
import time
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WebhookError(ValueError):
    pass


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise WebhookError("webhook URL must be an absolute http or https URL")
    host = parsed.hostname
    settings = get_settings()
    if settings.environment.lower() != "production":
        return url.strip()
    if host in {"localhost", "localhost.localdomain"}:
        raise WebhookError("localhost webhooks are disabled in production")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise WebhookError("webhook host could not be resolved") from exc
    for info in addresses:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebhookError("webhook host resolves to a non-public address")
    return url.strip()


def post_webhook(url: str, payload: dict, headers: dict[str, str] | None, timeout: float) -> int:
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(url, json=payload, headers=headers or {})
        response.raise_for_status()
        return response.status_code


def deliver_webhook(url: str, payload: dict, headers: dict[str, str] | None, timeout: float) -> tuple[str, int | None, str | None, int]:
    delay = 0.2
    last_error = "delivery failed"
    attempts = 0
    for attempt in range(1, 4):
        attempts = attempt
        try:
            code = post_webhook(url, payload, headers, timeout)
            return "success", code, None, attempts
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning("webhook delivery attempt failed", extra={"attempt": attempt})
            if attempt < 3:
                time.sleep(delay)
                delay = min(delay * 2, 2.0)
    return "failed", None, last_error, attempts
