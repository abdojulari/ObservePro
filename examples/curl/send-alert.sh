#!/bin/sh
set -eu
URL="${OBSERVE_URL:-http://localhost:8000}"
curl -sS -X POST "$URL/api/v1/alerts" \
  -H "Authorization: Bearer ${OBSERVE_API_KEY:?set OBSERVE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Payment failure rate exceeded threshold",
    "message": "Payment failures are above the configured threshold",
    "severity": "CRITICAL",
    "service": "payment-service",
    "environment": "production",
    "fingerprint": "payment-failure-rate",
    "attributes": {"failure_rate": 12.5, "threshold": 5.0}
  }'
echo
