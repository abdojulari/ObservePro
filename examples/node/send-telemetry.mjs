// Generic HTTP integration. Node 18+ has fetch. No packages required.
const endpoint = process.env.OBSERVE_URL ?? "http://localhost:8000";
const apiKey = process.env.OBSERVE_API_KEY;
if (!apiKey) {
  console.error("Set OBSERVE_API_KEY");
  process.exit(1);
}

const response = await fetch(`${endpoint}/api/v1/logs`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    severity: "ERROR",
    message: "Payment processing failed",
    service: "payment-service",
    environment: "production",
    attributes: { order_id: "order-123", payment_provider: "example-provider" },
  }),
});

if (!response.ok) {
  console.error(response.status, await response.text());
  process.exit(1);
}
console.log(await response.json());
