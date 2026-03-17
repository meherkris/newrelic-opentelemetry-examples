# AI Sample App - Microsoft Agent Framework with Langfuse and OpenTelemetry (Python)

This is a sample AI application demonstrating **AI Agent observability** using [Microsoft Agent Framework](https://github.com/microsoft/agent-framework), [Langfuse SDK](https://langfuse.com/docs), and [OpenTelemetry](https://opentelemetry.io/). It shows how to instrument a FastAPI application with an agent that uses tools, trace the complete agent execution flow, and export telemetry data through an OpenTelemetry Collector to New Relic.

 For more details on the Langfuse Microsoft Agent Framework integration, see the [official Langfuse documentation](https://langfuse.com/integrations/frameworks/microsoft-agent-framework)

The application exposes a `/chat` endpoint backed by a `MathAssistant` agent with `add` and `subtract` tools. The framework's native OpenTelemetry instrumentation (via `configure_otel_providers`) captures detailed traces of agent invocations, LLM calls, and tool executions. Traces are exported via OTLP to a local collector which forwards them to New Relic.

## What telemetry is captured?

The Microsoft Agent Framework with `configure_otel_providers` captures:

- **Traces**: Full agent execution spans including LLM calls, tool invocations, and agent orchestration
- **GenAI attributes**: `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Agent attributes**: `gen_ai.operation.name` on agent and LLM spans
- **Sensitive data**: Prompt and completion text captured when `enable_sensitive_data=True` is set

> **Note:** `configure_otel_providers(enable_sensitive_data=True)` is required to capture prompt/completion text in traces. Without it, only metadata (token counts, model names) is recorded.

## Requirements

- [Python 3.10 or later](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [A New Relic account](https://one.newrelic.com/)
- [A New Relic license key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#license-key)
- [An OpenAI API key](https://platform.openai.com/api-keys)
- [A Langfuse account](https://langfuse.com/) with public and secret keys

## Project structure

```
microsoft-agent-framework-langfuse/
├── otel-collector/
│   ├── docker-compose.yml      # Docker setup for OpenTelemetry Collector
│   └── otel-config.yaml        # Collector configuration with routing to New Relic
├── app.py                       # FastAPI application with Microsoft Agent Framework
├── requirements.txt             # Python dependencies
├── .env.template                # Example environment variables
└── README.md                   # This file
```

## Running the application

### 1. Configure environment variables

Create your `.env` file from the template and update the values:

```shell
cp .env.template .env
# Edit .env with your API keys
```

> **Note:** The `OTEL_SERVICE_NAME` environment variable in `.env.template` is automatically picked up by the OpenTelemetry SDK — no explicit code is needed to set the service name in the application.

### 2. Start the OpenTelemetry Collector

```shell
cd otel-collector
docker compose up -d
```

Verify the collector is running:

```shell
docker compose ps
docker compose logs -f otel-collector
```

### 3. Run the Python application

```shell
# Create and activate a virtual environment (use Python 3.12)
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

The API will start on `http://localhost:8000`.

### 4. Test the endpoint

```shell
# Simple addition
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 100 + 51?"}'

# Multiple operations
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 100 + 51 and then subtract 200?"}'
```

### 5. Stop the application

```shell
# Stop the collector
cd otel-collector
docker compose down
```

## Viewing your data in New Relic

> **Note:** It may take **3–5 minutes** after sending requests for data to appear in the AI Responses table and Span views in New Relic.

Navigate to **New Relic > All Entities > Services - OpenTelemetry** and find the service named `langfuse-microsoft-agent-framework-app`.

You can also use these NRQL queries to verify data is flowing:

```sql
-- Verify traces are being received
FROM Span
SELECT count(*)
WHERE service.name = 'langfuse-microsoft-agent-framework-app'
SINCE 5 minutes ago

-- View gen_ai spans with token usage
FROM Span
SELECT gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.request.model, duration
WHERE service.name = 'langfuse-microsoft-agent-framework-app'
SINCE 5 minutes ago

-- View agent and tool spans
FROM Span
SELECT name, gen_ai.operation.name, duration
WHERE service.name = 'langfuse-microsoft-agent-framework-app'
SINCE 5 minutes ago
```

For AI-specific monitoring, check the **AI Monitoring** section in New Relic for detailed insights into model performance, token usage, and response quality.

### Enabling AI Monitoring views

The OTel Collector configuration in this example already includes a `resource/ai_enabled` processor that adds the `aiEnabledApp: true` tag to all telemetry. This tag tells New Relic to recognize the service as an AI entity and enables the AI Responses and other AI-specific pages.

If you are not able to see the pages, you can manually apply the custom tag to your AI OTel entity in New Relic:

- **Tag:** `aiEnabledApp: true`

You can add this tag via **New Relic > All Entities > (your service) > ... > Add tags > `aiEnabledApp: true`**.

## Trace structure

For a typical agent request like "What is 100 + 51?", you'll see **4 spans** representing the agent execution:

1. **`invoke_agent MathAssistant`** - Root span covering the full agent session
2. **`chat gpt-4o`** - First LLM call (decides to call the `add` tool)
3. **`execute_tool add`** - Python function execution returning the result
4. **`chat gpt-4o`** - Second LLM call (synthesizes the final answer from tool results)

## OTel Collector configuration

The [otel-config.yaml](otel-collector/otel-config.yaml) uses a routing-only configuration — no attribute transformations are needed because the Microsoft Agent Framework produces OTel GenAI semantic convention attributes natively. Traces are routed to New Relic.

## Port Reference

- **8000** — FastAPI app
- **4317** — OTEL Collector gRPC
- **4318** — OTEL Collector HTTP

## Troubleshooting

**No spans in collector logs**
- Check `OTEL_EXPORTER_OTLP_ENDPOINT` includes the full path: `http://localhost:4318/v1/traces`

**No data in New Relic**
- Verify `NEW_RELIC_LICENSE_KEY` is set in the collector environment
- Check collector logs: `cd otel-collector && docker compose logs otel-collector`
- Wait 3-4 minutes for data to appear

**Collector fails to start**
- Check config syntax: `cd otel-collector && docker compose logs otel-collector`
- After any config change, restart: `cd otel-collector && docker compose restart otel-collector`
