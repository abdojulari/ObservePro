# observability-client

Install from a checkout:

```bash
pip install -e ./sdk/python
```

The client sends logs, events, and alerts to the ObservePro HTTP API and uses the
OpenTelemetry SDK for traces. If the server is down, calls return immediately
after queueing, retries are bounded, and a full buffer drops new events instead
of blocking the application.

See the package docstring and `examples/basic.py`.
