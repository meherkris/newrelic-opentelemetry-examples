# LangChain Math Tutor Agent — OpenTelemetry + New Relic

A FastAPI application demonstrating AI agent observability using LangChain, OpenTelemetry, and New Relic.

## What It Does

A math tutor agent powered by `gpt-4o` that answers math questions using tool calls (`add`, `subtract`, `multiply`, `divide`). All agent activity — LLM calls, tool executions, token usage — is automatically traced and sent to New Relic via an OTel Collector.

## Stack

| Component | Technology |
|-----------|-----------|
| LLM Framework | LangChain 0.3+ (`create_openai_tools_agent` + `AgentExecutor`) |
| LLM | OpenAI `gpt-4o` |
| Web Server | FastAPI + Uvicorn |
| Instrumentation | `opentelemetry-instrumentation-langchain` (`LangchainInstrumentor`) |
| Telemetry export | OTel SDK → OTLP HTTP → OTel Collector → New Relic |

## Project Structure

```
langchain-test/
├── langchain_app.py                      # FastAPI app + agent + OTel setup
├── langchain-test-collector-config.yaml  # OTel Collector config (active)
├── docker-compose-langchain-test.yaml    # Docker Compose for collector
├── requirements.txt                      # Python dependencies
├── .env.example                          # Environment variable template
├── DOCUMENTATION.md                      # Full technical documentation
└── README.md                             # This file
```

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file with:

```bash
OPENAI_API_KEY=sk-...
NEW_RELIC_LICENSE_KEY=your-nr-license-key
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=langchain-test
```

### 3. Start the OTel Collector

```bash
docker-compose -f docker-compose-langchain-test.yaml up -d
```

### 4. Start the application

```bash
uvicorn langchain_app:app --reload --host 0.0.0.0 --port 8000
```

### 5. Send a request

```bash
curl -X POST http://localhost:8000/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 20 plus 30?"}'
```

**Response:**
```json
{
  "response": "20 plus 30 equals 50."
}
```

## How Observability Works

### Auto-instrumented by `LangchainInstrumentor`

Every LangChain operation is automatically traced with Traceloop semantic conventions:

- `traceloop.workflow.name` → agent name (`MathTutorAgent`)
- `traceloop.span.kind` → span type (`workflow`, `tool`, `task`)
- `traceloop.entity.name` → tool name (`add_numbers`)
- `gen_ai.*` attributes → LLM model, tokens, prompts, completions

### Manually set in app code

`gen_ai.output.messages` is set on the root span as a JSON array for New Relic AI Responses visibility:

```python
span.set_attribute("gen_ai.output.messages", json.dumps([{
    "role": "assistant",
    "content": result["output"]
}]))
```

### OTel Collector attribute mapping

The collector maps Traceloop attributes to Gen AI semantic conventions:

```yaml
# gen_ai.agent.name set only on workflow spans
- 'set(attributes["gen_ai.agent.name"], attributes["traceloop.workflow.name"]) where attributes["traceloop.span.kind"] == "workflow"'
# gen_ai.tool.name set only on tool spans
- 'set(attributes["gen_ai.tool.name"], attributes["traceloop.entity.name"]) where attributes["traceloop.span.kind"] == "tool"'
```

### Trace structure

```
agent_response (root span — manually created)
  └── gen_ai.output.messages: [{"role": "assistant", "content": "..."}]
      ├── MathTutorAgent (workflow) → gen_ai.agent.name: MathTutorAgent
      ├── ChatPromptTemplate (task)
      ├── ChatOpenAI LLM Call #1 → decides to call add_numbers(20, 30)
      ├── add_numbers (tool) → gen_ai.tool.name: add_numbers
      └── ChatOpenAI LLM Call #2 → final response
```

### Enable New Relic AI Monitoring

To surface your app in New Relic's **AI Monitoring** section, add `aiEnabledApp: "true"` to the `resource` processor in your OTel Collector config ([`nr-config/langchain-test-collector-config.yaml`](nr-config/langchain-test-collector-config.yaml)):

```yaml
processors:
  resource:
    attributes:
      - key: aiEnabledApp
        value: "true"
        action: insert
```

> This is required for OTel-instrumented apps. Without it, spans arrive in New Relic but the app will not appear in the AI Monitoring entity list. Apps using the New Relic agent get this automatically.

## Viewing in New Relic

- **APM → Services → langchain-test** — service overview and traces
- **Distributed Tracing** — full span waterfall
- **AI Monitoring** — token usage, tool calls, agent responses
- **NRQL query:** `SELECT * FROM Span WHERE gen_ai.agent.name = 'MathTutorAgent'`

## Debugging

```bash
# Stream collector logs
docker logs langchain-test-collector -f

# Check Gen AI attributes are flowing
docker logs langchain-test-collector 2>&1 | grep "gen_ai\."

# Check agent and tool names are set
docker logs langchain-test-collector 2>&1 | grep "gen_ai.agent.name\|gen_ai.tool.name"
```

## Full Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for:
- Complete architecture and data flow
- All collector processor and pipeline configuration
- Full attribute reference table
- Known limitations and debugging tips
