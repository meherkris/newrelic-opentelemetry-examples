# AI Sample App - Autogen Multi-Agent with Langfuse and OpenTelemetry (Python)

This is a sample AI application demonstrating **AI Agent observability** using [Langfuse SDK](https://langfuse.com/docs), [Microsoft Autogen](https://microsoft.github.io/autogen/), and [OpenTelemetry](https://opentelemetry.io/). It shows how to instrument a FastAPI application with a multi-agent system, trace the complete agent execution flow, and export telemetry data through an OpenTelemetry Collector to New Relic.

 For more details on the Langfuse Autogen integration, see the [official Langfuse documentation](https://langfuse.com/integrations/frameworks/autogen)

The application exposes a `/chat` endpoint backed by two collaborative Autogen agents (`MathAgent` and `ValidatorAgent`) orchestrated via `RoundRobinGroupChat`. The Langfuse SDK captures detailed traces of the entire multi-agent execution flow (including agent communication, tool calls, and LLM interactions via `OpenAIInstrumentor`), and exports them via OTLP to a local collector. The collector routes traces to New Relic.

## What telemetry is captured?

The Langfuse SDK with OpenAIInstrumentor captures:

- **Traces**: Full multi-agent execution spans including LLM calls, tool invocations, agent-to-agent message passing, and orchestration
- **GenAI attributes**: `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- **Agent attributes**: Agent communication spans with `sender_agent_class`, `recipient_agent_class`, `messaging.operation`, `messaging.destination`
- **Tool execution**: Tool calls represented as message types within the agent communication flow

## Requirements

- [Python 3.11 or 3.12](https://www.python.org/downloads/) (Python 3.14+ not yet supported due to pydantic v1 compatibility)
- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [A New Relic account](https://one.newrelic.com/)
- [A New Relic license key](https://docs.newrelic.com/docs/apis/intro-apis/new-relic-api-keys/#license-key)
- [An OpenAI API key](https://platform.openai.com/api-keys)
- [A Langfuse account](https://langfuse.com/) with public and secret keys

## Project structure

```
autogen-langfuse/
├── otel-collector/
│   ├── docker-compose.yml      # Docker setup for OpenTelemetry Collector
│   └── otel-config.yaml        # Collector configuration with routing to New Relic and Langfuse
├── app.py                       # FastAPI application with Autogen multi-agent system
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
  -d '{"prompt": "What is 4 + 2?"}'

# Multiple operations
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 123 + 51 and 89 - 9?"}'
```

### 5. Stop the application

```shell
# Stop the collector
cd otel-collector
docker compose down
```

## Viewing your data in New Relic

> **Note:** It may take **3–5 minutes** after sending requests for data to appear in the AI Responses table and Span views in New Relic.

Navigate to **New Relic > All Entities > Services - OpenTelemetry** and find the service named `langfuse-autogen-app`.

You can also use these NRQL queries to verify data is flowing:

```sql
-- Verify traces are being received
FROM Span
SELECT count(*)
WHERE service.name = 'langfuse-autogen-app'
SINCE 5 minutes ago

-- View gen_ai spans with token usage
FROM Span
SELECT gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, gen_ai.request.model, duration
WHERE service.name = 'langfuse-autogen-app'
SINCE 5 minutes ago

-- View agent communication spans
FROM Span
SELECT name, duration, messaging.operation, messaging.destination
WHERE service.name = 'langfuse-autogen-app'
SINCE 5 minutes ago
```

For AI-specific monitoring, check the **AI Monitoring** section in New Relic for detailed insights into model performance, token usage, and response quality.

### Enabling AI Monitoring views

The OTel Collector configuration in this example already includes a `resource/ai_enabled` processor that adds the `aiEnabledApp: true` tag to all telemetry. This tag tells New Relic to recognize the service as an AI entity and enables the AI Responses and other AI-specific pages.

If you are not able to see the pages, you can manually apply the custom tag to your AI OTel entity in New Relic:

- **Tag:** `aiEnabledApp: true`

You can add this tag via **New Relic > All Entities > (your service) > ... > Add tags > `aiEnabledApp: true`**.

## Trace structure

For a typical agent request like "What is 4 + 2?", you'll see **31+ spans** representing the multi-agent communication flow:

1. **Root span** (`calculator-agent`) - Langfuse parent context
2. **RoundRobinGroupChatManager** - Orchestration of agent turns
3. **MathAgent processing** - Agent receives task, makes OpenAI API call with tool request, executes `add_tool`, summarizes result
4. **ValidatorAgent processing** - Agent validates the calculation, responds with "APPROVED"
5. **Message passing spans** - `process`, `create`, `send`, `publish`, `ack` operations between agents

Each agent turn includes OpenAI LLM call spans (via `OpenAIInstrumentor`) with `gen_ai.system`, `gen_ai.request.model`, and token usage attributes.

## OTel Collector configuration

The [otel-config.yaml](otel-collector/otel-config.yaml) uses a routing-only configuration — no attribute transformations are needed because Autogen with `OpenAIInstrumentor` produces OTel GenAI semantic convention attributes natively. Traces are routed to New Relic.
