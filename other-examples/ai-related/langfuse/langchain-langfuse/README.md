# AI Sample App - LangChain Agent with Langfuse and OpenTelemetry (Python)

This is a sample AI application demonstrating **AI Agent observability** using [Langfuse SDK](https://langfuse.com/docs), [LangChain/LangGraph](https://python.langchain.com/), and [OpenTelemetry](https://opentelemetry.io/). It shows how to instrument a FastAPI application with an agent that uses tools, trace the complete agent execution flow, and export telemetry data through an OpenTelemetry Collector to New Relic.

 For more details on the Langfuse LangChain integration, see the [official Langfuse documentation](https://langfuse.com/integrations/frameworks/langchain)

The application exposes a `/chat` endpoint backed by a LangChain agent with custom tools (`add_numbers`, `subtract_numbers`). The Langfuse SDK captures detailed traces of the entire agent execution flow (including agent reasoning, tool calls, and LLM interactions), and exports them via OTLP to a local collector. The collector transforms Langfuse attributes to [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) and forwards them to New Relic.

## What telemetry is captured?

The Langfuse SDK with OTel Collector transform processor captures:

- **Traces**: Full agent execution spans including LLM calls, tool invocations, and agent orchestration
- **GenAI attributes**: `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Agent attributes**: `gen_ai.agent.name` on agent orchestration spans, `gen_ai.tool.name` on tool execution spans
- **Response metadata**: `gen_ai.response.id` (OpenAI response ID), `gen_ai.response.finish_reasons`

## Requirements

- [Python 3.11 or 3.12](https://www.python.org/downloads/) (Python 3.14+ not yet supported due to pydantic v1 compatibility)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [A New Relic account](https://one.newrelic.com/)
- [A New Relic license key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#license-key)
- [An OpenAI API key](https://platform.openai.com/api-keys)
- [A Langfuse account](https://langfuse.com/) with public and secret keys

## Project structure

```
langchain-langfuse/
├── otel-collector/
│   ├── docker-compose.yml      # Docker setup for OpenTelemetry Collector
│   └── otel-config.yaml        # Collector configuration with Langfuse → GenAI transforms
├── app.py                       # FastAPI application with Langfuse instrumentation
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
# Create and activate a virtual environment (use Python 3.11 or 3.12)
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
  -d '{"prompt": "What is 900 + 51 and 89 - 9?"}'
```

### 5. Stop the application

```shell
# Stop the collector
cd otel-collector
docker compose down
```

## Viewing your data in New Relic

> **Note:** It may take **3–5 minutes** after sending requests for data to appear in the AI Responses table and Span views in New Relic.

Navigate to **New Relic > All Entities > Services - OpenTelemetry** and find the service named `langfuse-langchain-app`.

You can also use these NRQL queries to verify data is flowing:

```sql
-- Verify traces are being received
FROM Span
SELECT count(*)
WHERE service.name = 'langfuse-langchain-app'
SINCE 5 minutes ago

-- View gen_ai spans with token usage
FROM Span
SELECT gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.request.model, duration
WHERE service.name = 'langfuse-langchain-app'
SINCE 5 minutes ago

-- View agent and tool spans
FROM Span
SELECT gen_ai.agent.name, gen_ai.tool.name, name, duration
WHERE service.name = 'langfuse-langchain-app'
  AND (gen_ai.agent.name IS NOT NULL OR gen_ai.tool.name IS NOT NULL)
SINCE 5 minutes ago
```

For AI-specific monitoring, check the **AI Monitoring** section in New Relic for detailed insights into model performance, token usage, and response quality.

### Enabling AI Monitoring views

The OTel Collector configuration in this example already includes a `resource/ai_enabled` processor that adds the `aiEnabledApp: true` tag to all telemetry. This tag tells New Relic to recognize the service as an AI entity and enables the AI Responses and other AI-specific pages.

If you are not able to see the pages, you can manually apply the custom tag to your AI OTel entity in New Relic:

- **Tag:** `aiEnabledApp: true`

You can add this tag via **New Relic > All Entities > (your service) > ... > Add tags > `aiEnabledApp: true`**.

## Trace structure

For a typical agent request, you'll see **7 spans** representing the ReAct pattern:

1. **Agent span** (`math_tutor_agent`) - Top-level orchestration
2. **Model node (1st call)** - LangGraph chain invoking the LLM
3. **ChatOpenAI (1st call)** - OpenAI API call that returns tool_calls
4. **Tools node** - LangGraph chain handling tool execution
5. **Tool execution** - Your actual `add_numbers` or `subtract_numbers` function
6. **Model node (2nd call)** - LangGraph chain invoking LLM again with tool results
7. **ChatOpenAI (2nd call)** - OpenAI API call to generate natural language response

## OTel Collector attribute mapping

The [otel-config.yaml](otel-collector/otel-config.yaml) transforms Langfuse-specific attributes to OTel GenAI semantic conventions:

| Langfuse attribute | GenAI attribute | Notes |
|---|---|---|
| `langfuse.observation.model.name` | `gen_ai.request.model`, `gen_ai.response.model` | Model name |
| `langfuse.observation.metadata.ls_provider` | `gen_ai.system` | e.g., "openai" |
| `langfuse.observation.usage_details` | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Parsed from JSON |
| `langfuse.observation.type` == "tool" | `gen_ai.tool.name` | Extracted from span name |
| `langfuse.observation.type` == "agent" | `gen_ai.agent.name` | Extracted from span name |
| Response metadata | `gen_ai.response.id`, `gen_ai.response.finish_reasons` | Extracted from output JSON |
