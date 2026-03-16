# AI Sample App - Strands Agent with Langfuse and OpenTelemetry (Python)

This is a sample AI application demonstrating **AI Agent observability** using [Strands Agents](https://github.com/strands-agents/sdk-python), [Langfuse SDK](https://langfuse.com/docs), and [OpenTelemetry](https://opentelemetry.io/). It shows how to instrument a FastAPI application with an agent that uses tools, trace the complete agent execution flow, and export telemetry data through an OpenTelemetry Collector to New Relic.

 For more details on the Langfuse Strands Agents integration, see the [official Langfuse documentation](https://langfuse.com/integrations/frameworks/strands-agents) and the [Strands observability sample notebook](https://github.com/strands-agents/samples/blob/c4b447332d87429c5f986e948db91a454d8135f3/01-tutorials/01-fundamentals/08-observability-and-evaluation/Observability-and-Evaluation-sample.ipynb)

The application exposes a `/chat` endpoint backed by a Strands math tutor agent with custom tools (`add_numbers`, `subtract_numbers`). Strands' built-in `StrandsTelemetry` emits `gen_ai.*` semantic convention traces natively — no external instrumentor needed. The OTel Collector transforms span events into span attributes and forwards them to New Relic.

## What telemetry is captured?

The Strands `StrandsTelemetry` captures:

- **Traces**: Full agent execution spans including LLM calls, tool invocations, and agent reasoning
- **GenAI attributes**: `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Agent attributes**: `gen_ai.operation.name` on agent and LLM spans
- **Message content**: `gen_ai.input.messages` and `gen_ai.output.messages` (extracted from span events by the OTel Collector)

## Requirements

- [Python 3.12 or later](https://www.python.org/downloads/)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [A New Relic account](https://one.newrelic.com/)
- [A New Relic license key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#license-key)
- [An OpenAI API key](https://platform.openai.com/api-keys)
- [A Langfuse account](https://langfuse.com/) with public and secret keys

## Project structure

```
strands-langfuse/
├── otel-collector/
│   ├── docker-compose.yml      # Docker setup for OpenTelemetry Collector
│   └── otel-config.yaml        # Collector configuration with event-to-attribute transforms
├── app.py                       # FastAPI application with Strands agent and tools
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
  -d '{"prompt": "What is 2 + 2 and the answer subtract by 9?"}'

# Subtraction
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 100 - 37?"}'
```

### 5. Stop the application

```shell
# Stop the collector
cd otel-collector
docker compose down
```

## Viewing your data in New Relic

> **Note:** It may take **3–5 minutes** after sending requests for data to appear in the AI Responses table and Span views in New Relic.

Navigate to **New Relic > All Entities > Services - OpenTelemetry** and find the service named `langfuse-strands-app`.

You can also use these NRQL queries to verify data is flowing:

```sql
-- Verify traces are being received
FROM Span
SELECT count(*)
WHERE service.name = 'langfuse-strands-app'
SINCE 5 minutes ago

-- View gen_ai spans with token usage
FROM Span
SELECT gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.request.model, duration
WHERE service.name = 'langfuse-strands-app'
SINCE 5 minutes ago

-- View agent and tool spans
FROM Span
SELECT name, gen_ai.operation.name, duration
WHERE service.name = 'langfuse-strands-app'
SINCE 5 minutes ago
```

For AI-specific monitoring, check the **AI Monitoring** section in New Relic for detailed insights into model performance, token usage, and response quality.

### Enabling AI Monitoring views

The OTel Collector configuration in this example already includes a `resource/ai_enabled` processor that adds the `aiEnabledApp: true` tag to all telemetry. This tag tells New Relic to recognize the service as an AI entity and enables the AI Responses and other AI-specific pages.

If you are not able to see the pages, you can manually apply the custom tag to your AI OTel entity in New Relic:

- **Tag:** `aiEnabledApp: true`

You can add this tag via **New Relic > All Entities > (your service) > ... > Add tags > `aiEnabledApp: true`**.

## Trace structure

For a typical agent request, Strands produces spans representing:

1. **Agent span** - Top-level agent orchestration
2. **LLM call spans** - OpenAI API calls with tool selection and final response generation
3. **Tool execution spans** - `add_numbers` or `subtract_numbers` function executions

Strands emits `gen_ai.*` attributes natively, so no attribute transformation is needed for the core telemetry. The OTel Collector only transforms span events (like `gen_ai.client.inference.operation.details`) into span attributes for platform compatibility.

## OTel Collector attribute mapping

The [otel-config.yaml](otel-collector/otel-config.yaml) uses a `transform/gen_ai_latest` processor to extract span event data into span attributes:

| Source | Target span attribute | Notes |
|---|---|---|
| `gen_ai.input.messages` (from span event) | `gen_ai.input.messages` | Extracted from `gen_ai.client.inference.operation.details` event |
| `gen_ai.output.messages` (from span event) | `gen_ai.output.messages` | Extracted from `gen_ai.client.inference.operation.details` event |
| `finish_reason` (from `gen_ai.output.messages` JSON) | `gen_ai.response.finish_reasons` | Parsed via regex from the `gen_ai.output.messages` JSON string (e.g. `end_turn`, `tool_use`) |

The `gen_ai.response.finish_reasons` attribute is extracted at the **span** context level using OTTL's `ExtractPatterns` function. It parses the `finish_reason` field from the JSON-encoded `gen_ai.output.messages` attribute and promotes it to a top-level span attribute for easier querying.

This requires `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` to be set in the application environment (already configured in `.env.template`).
