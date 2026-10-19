"""Example service. Create the client before FastAPI instrumentation so tracing is installed.

pip install -e ../../sdk/python
pip install -r requirements.txt
OBSERVE_API_KEY=... uvicorn app:app --port 8080
"""

import os

from fastapi import FastAPI
from observability_client import ObservabilityClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

client = ObservabilityClient(
    endpoint=os.environ.get("OBSERVE_URL", "http://localhost:8000"),
    api_key=os.environ.get("OBSERVE_API_KEY", "missing"),
    service_name="payment-service",
    environment=os.environ.get("OBSERVE_ENVIRONMENT", "development"),
    service_version="1.0.0",
)

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)


@app.get("/pay")
def pay(order_id: str = "order-123") -> dict[str, str]:
    with client.start_span("process_payment") as span:
        span.set_attribute("payment.provider", "example-provider")
        span.set_attribute("order_id", order_id)
        client.info("Payment accepted", attributes={"order_id": order_id})
    return {"status": "ok", "order_id": order_id}
