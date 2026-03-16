# AI Sample App - LlamaIndex Agent with Langfuse and OpenTelemetry (Python)

This is a sample AI application demonstrating **AI Agent observability** using [Langfuse SDK](https://langfuse.com/docs), [LlamaIndex](https://docs.llamaindex.ai/), and [OpenTelemetry](https://opentelemetry.io/). It shows how to instrument a FastAPI application with a LlamaIndex agent that uses tools, trace the complete agent execution flow, and export telemetry data through an OpenTelemetry Collector to New Relic.

 For more details on the Langfuse LlamaIndex integration, see the [official Langfuse documentation](https://langfuse.com/integrations/frameworks/llamaindex)

The application exposes a `/chat` endpoint backed by a LlamaIndex `ReActAgent` with custom tools (`add`, `subtract`). The `LlamaIndexInstrumentor` captures detailed traces using OpenInference semantic conventions, and the OTel Collector transforms them to [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) before forwarding to New Relic and Langfuse.

## What telemetry is captured?

The LlamaIndexInstrumentor with OTel Collector transform processor captures:

- **Traces**: Full agent execution spans including LLM calls, tool invocations, and agent workflow orchestration
- **GenAI attributes**: `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Agent attributes**: `gen_ai.agent.name` on workflow spans, `gen_ai.operation.name` (`agent`, `chat`, `tool`)
- **Tool attributes**: `gen_ai.tool.name`, `gen_ai.tool.type`, `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`
- **Response metadata**: `gen_ai.response.id`, `gen_ai.response.finish_reasons`

## Requirements

- [Python 3.11 or 3.12](https://www.python.org/downloads/) (Python 3.14+ not yet supported due to pydantic v1 compatibility)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [A New Relic account](https://one.newrelic.com/)
- [A New Relic license key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#license-key)
- [An OpenAI API key](https://platform.openai.com/api-keys)
- [A Langfuse account](https://langfuse.com/) with public and secret keys

## Project structure

```
llamaIndex-langfuse/
├── otel-collector/
│   ├── docker-compose.yml      # Docker setup for OpenTelemetry Collector
│   └── otel-config.yaml        # Collector configuration with OpenInference → GenAI transforms
├── app.py                       # FastAPI application with ReActAgent
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

# Subtraction And Addition
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 100 + 51 and answer subtract 200?"}'
```

### 5. Stop the application

```shell
# Stop the collector
cd otel-collector
docker compose down
```

## Viewing your data in New Relic

> **Note:** It may take **3–5 minutes** after sending requests for data to appear in the AI Responses table and Span views in New Relic.

Navigate to **New Relic > All Entities > Services - OpenTelemetry** and find the service named `langfuse-llamaindex-app`.

You can also use these NRQL queries to verify data is flowing:

```sql
-- Verify traces are being received
FROM Span
SELECT count(*)
WHERE service.name = 'langfuse-llamaindex-app'
SINCE 5 minutes ago

-- View gen_ai spans with token usage
FROM Span
SELECT gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.request.model, duration
WHERE service.name = 'langfuse-llamaindex-app'
SINCE 5 minutes ago

-- View agent and tool spans
FROM Span
SELECT gen_ai.agent.name, gen_ai.tool.name, name, duration
WHERE service.name = 'langfuse-llamaindex-app'
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

For a typical agent request like "What is 4 multiply with 2?", you'll see **15 spans** representing the agent workflow:

- **8 CHAIN spans** (workflow orchestration): `ReActAgent.run`, `init_run`, `setup_agent`, `run_agent_step`, `parse_agent_output`, `call_tool`, `aggregate_tool_results`
- **4 LLM spans** (OpenAI interactions): `_prepare_chat_with_tools` and `astream_chat` for each LLM call
- **1 TOOL span**: `FunctionTool.acall` (add or subtract execution)
- **1 Root span**: `calculator-agent` (Langfuse context)

Token usage per request is approximately 127 input + 17 output tokens (tool selection) and 152 input + 10 output tokens (final response), totaling ~306 tokens.

> **Note**: The high span count (15) is normal for LlamaIndex. It provides deep visibility into the agent's workflow but creates more spans than other frameworks.

## OTel Collector attribute mapping

The [otel-config.yaml](otel-collector/otel-config.yaml) transforms OpenInference attributes (from LlamaIndex) to OTel GenAI semantic conventions:

| OpenInference attribute | GenAI attribute | Notes |
|---|---|---|
| `llm.system` | `gen_ai.system` | e.g., "openai" |
| `llm.model_name` | `gen_ai.request.model`, `gen_ai.response.model` | Model name |
| `llm.token_count.prompt` | `gen_ai.usage.input_tokens` | Input token count |
| `llm.token_count.completion` | `gen_ai.usage.output_tokens` | Output token count |
| `tool.name` | `gen_ai.tool.name` | Tool function name |
| `openinference.span.kind` == "CHAIN" | `gen_ai.operation.name` = "agent" | Agent workflow spans |
| `openinference.span.kind` == "LLM" | `gen_ai.operation.name` = "chat" | LLM call spans |
| `openinference.span.kind` == "TOOL" | `gen_ai.operation.name` = "tool" | Tool execution spans |
| `input.value` / `output.value` | — | Not transformable (see note below) |

> **Note on `gen_ai.input.messages` / `gen_ai.output.messages`:** The `openinference-instrumentation-llama-index` library emits `input.value` and `output.value` as plain strings, not in the structured JSON format expected by the [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). The OTel Collector's transform processor cannot reshape these into the required `[{"role": "...", "content": "..."}]` format. To work around this, the application code manually sets `gen_ai.input.messages` and `gen_ai.output.messages` on the root span:
>
> ```python
> span = trace.get_current_span()
> span.set_attribute("gen_ai.input.messages", json.dumps([{"role": "user", "content": request.prompt}]))
> span.set_attribute("gen_ai.output.messages", json.dumps([{"role": "assistant", "content": str(response)}]))
> ```
