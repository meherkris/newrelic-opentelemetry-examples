# Microsoft Agent Framework FastAPI with OpenTelemetry → New Relic

A FastAPI application using the Microsoft Agent Framework with a `WeatherAssistant` agent that answers questions via a `get_weather` tool. The Microsoft Agent Framework emits OpenTelemetry GenAI telemetry natively; an OTel Collector forwards traces, metrics, and logs to New Relic.

## Architecture

```
FastAPI App (Microsoft Agent Framework)
    └── configure_otel_providers(enable_sensitive_data=True)
    │     └── native gen_ai.* spans + metrics + logs
    └── OTLPSpanExporter (HTTP)
            ↓
OTel Collector (port 4318)
    └── batch processor
    └── debug exporter        →  logs telemetry to stdout
    └── otlp_http/newrelic     →  forwards to New Relic
            ↓
        New Relic
```

## Native Instrumentation — One Call

The Microsoft Agent Framework has built-in OpenTelemetry support. A single call configures the trace, metric, and log providers and instruments the agent, its LLM calls, and its tool executions — no separate LLM auto-instrumentation package and no manual spans:

```python
from agent_framework.observability import configure_otel_providers

configure_otel_providers(enable_sensitive_data=True)
```

`enable_sensitive_data=True` also attaches prompt and completion content to the spans.

## Trace Structure

Each request to `/chat` produces the following span hierarchy:

```
invoke_agent WeatherAssistant     ← agent span (gen_ai.agent.name = WeatherAssistant)
  chat {model}                    ← LLM call: decides to call the tool
  execute_tool get_weather        ← tool execution (gen_ai.tool.name = get_weather)
  chat {model}                    ← LLM call: final response
```

Key attributes visible in New Relic:
- `gen_ai.agent.name` — `WeatherAssistant`
- `gen_ai.tool.name` — `get_weather`
- `gen_ai.request.model` — from `OPENAI_RESPONSES_MODEL_ID`
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`

## Metrics

The Microsoft Agent Framework emits GenAI metrics natively, exported over OTLP alongside traces and logs:

- `gen_ai.client.token.usage` — input / output token counts per LLM call
- `gen_ai.client.operation.duration` — LLM operation latency

> Metrics are exported using `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`. The framework defaults its metric exporter to gRPC, which is dropped against the collector's HTTP port (4318), so the protocol is set explicitly in `.env`.

## Prerequisites

- Python 3.10+
- Docker
- OpenAI API key
- New Relic ingest (license) key

## Setup

### 1. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `OPENAI_BASE_URL` | OpenAI API base URL |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_RESPONSES_MODEL_ID` | Model to use (e.g. `gpt-4o`) |
| `NEW_RELIC_API_KEY` | New Relic ingest key (used by the collector) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector endpoint (`http://localhost:4318`) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` (required for metrics over HTTP) |
| `OTEL_SERVICE_NAME` | Service name in New Relic |

### 3. Start the OTel Collector

Docker Compose reads `NEW_RELIC_API_KEY` from your `.env` and passes it to the collector:

```bash
docker compose up -d
```

Confirm it is running:

```bash
docker compose logs -f
```

### 4. Run the application

```bash
python app.py
```

The app starts on port 8000.

## API

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Paris?"}'
```

## Available Tools

- `get_weather(location)` — returns a weather report for the given location

## Collector Configuration

The collector ([`otel-config.yaml`](otel-config.yaml)) receives OTLP on ports 4318 (HTTP) and 4317 (gRPC), batches telemetry, and exports it to two destinations:

- `debug` — logs full telemetry to the collector's stdout for local troubleshooting
- `otlp_http/newrelic` — forwards traces, metrics, and logs to New Relic with gzip compression and `NEW_RELIC_API_KEY` as the `api-key` header

The endpoint is set to New Relic's staging OTLP endpoint (`https://staging-otlp.nr-data.net`). For US production use `https://otlp.nr-data.net`; for EU use `https://otlp.eu01.nr-data.net`.

## Viewing in New Relic

Open **All Entities → Services - OpenTelemetry** (or **AI Monitoring**) and select the service named by `OTEL_SERVICE_NAME`. Use **Distributed Tracing** and filter by `gen_ai.agent.name = WeatherAssistant` or `gen_ai.tool.name = get_weather`.

> To have an OTel-instrumented app surface in the New Relic **AI Monitoring** entity list, the telemetry must carry the `aiEnabledApp: "true"` resource attribute (apps using the New Relic agent get this automatically). It can be added via a `resource` processor in the collector config if the app does not already set it.

## Port Reference

- **8000** — FastAPI app
- **4318** — OTel Collector HTTP
- **4317** — OTel Collector gRPC
- **13133** — Collector health check
- **55679** — Collector zPages
- **1777** — Collector pprof

## Troubleshooting

**No data in New Relic**
- Verify `NEW_RELIC_API_KEY` is set in `.env`
- Check collector logs: `docker compose logs`

**No metrics, only traces**
- Confirm `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf` is set — the framework defaults metrics to gRPC, which is dropped against the HTTP collector port

**No spans reaching the collector**
- Confirm the collector was running before the app started

**Telemetry going somewhere other than the local collector**
- `load_dotenv()` does not override variables already set in your shell. If `OTEL_EXPORTER_OTLP_ENDPOINT` is exported in your environment, unset it or start the app with the value set explicitly: `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 python app.py`
