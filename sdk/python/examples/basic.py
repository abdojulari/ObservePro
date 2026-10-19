from observability_client import ObservabilityClient

client = ObservabilityClient(
    endpoint="http://localhost:8000",
    api_key="YOUR_PROJECT_API_KEY",
    service_name="payment-service",
    environment="development",
    console=True,
)

client.info("Payment service started")
client.warning("Payment retry initiated", attributes={"order_id": "order-123"})
client.error("Payment processing failed", attributes={"order_id": "order-123"})
client.alert(
    title="Payment processing failure",
    message="Payment provider is returning errors",
    severity="CRITICAL",
)
with client.start_span("process_payment") as span:
    span.set_attribute("payment.provider", "example-provider")
client.flush()
client.shutdown()
