# Telemetry Trust Gate

Building a reliability/safety gating service that combines rule-based checks with agentic LLM reasoning, wired into infra the candidate already knows (Go service, Redis event bus, k8s/Helm deploy).

**Live demo:** https://bucket-robotics.ashanpraba.com

The demo runs entirely in the browser against seeded data — no API keys,
no accounts, and no external services required.

## Stack

- Go
- Python
- Redis
- LangChain
- Bedrock
- Kubernetes
- Helm

## How it works

- Write a small Python script that emits synthetic robot telemetry events (position, torque, temp) at 1/sec into a Redis stream.
- A Go service that consumes the stream, runs threshold checks (e.g., torque > X), and forwards borderline/ambiguous events to a Python LangChain worker.
- LangChain worker calls Bedrock with a short prompt asking it to classify the event as safe/anomalous with a one-line justification.
- Go service aggregates results into a rolling 'trust score' stored in Redis and exposes it via a /status endpoint.
- Packaged the two services in a minimal Helm chart, deploy to a local kind cluster, and show the trust score flipping when you inject a bad telemetry burst.
- Record a 60-90s take: start the generator, show normal green status, inject anomaly, show gate flip red with LLM's justification in logs.

## Running locally

```bash
cd src
bash run.sh
```

Then open the printed URL. A prebuilt static version of the UI lives in
`src/web/` and can be opened directly with no server.
