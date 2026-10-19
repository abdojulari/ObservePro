#!/bin/sh
# Send one log. Requires OBSERVE_API_KEY. OBSERVE_URL defaults to http://localhost:8000.
set -eu
URL="${OBSERVE_URL:-http://localhost:8000}"
curl -sS -X POST "$URL/api/v1/logs" \
  -H "Authorization: Bearer ${OBSERVE_API_KEY:?set OBSERVE_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: curl-payment-failure" \
  -d '{
    "timestamp": "2026-10-19T18:00:00Z",
    "severity": "ERROR",
    "message": "Payment processing failed",
    "service": "payment-service",
    "environment": "production",
    "attributes": {"order_id": "order-123", "payment_provider": "example-provider"}
  }'
echo
