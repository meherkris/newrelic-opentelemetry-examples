# LangChain + OpenTelemetry + New Relic - AI Agent Observability

**Python version:** 3.9
**OpenTelemetry-SDK version:** 1.38.0+
**LangChain version:** 0.3.0+
**Instrumentation:** `opentelemetry-instrumentation-langchain` (`LangchainInstrumentor`)

---

## 1. Technology Stack Overview

### 1.1 What is LangChain?

LangChain is a framework for developing applications powered by language models. It provides:

- **Agents**: Agentic workflows that use LLMs to reason and decide which tools to call
- **Tools**: Function tools (decorated with `@tool`) that agents can invoke
- **AgentExecutor**: Runtime orchestrator that manages the agent's reasoning loop
- **Callbacks & Tracing**: Built-in integration with OpenTelemetry for observability

### 1.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER REQUEST                             │
│        POST /prompt: "What is 20 plus 30?"                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│          FastAPI Application (langchain_app.py)             │
│  • Receives HTTP POST request                               │
│  • Routes to /prompt endpoint                               │
│  • Manually creates root span "agent_response"              │
│  • Sets gen_ai.output.messages as JSON array on root span   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│     LangChain AgentExecutor (name="MathTutorAgent")         │
│  • Step 1: Agent reasons about the query                    │
│  • Step 2: Calls ChatOpenAI LLM with tools available        │
│  • Step 3: LLM decides to use add_numbers tool              │
│  • Step 4: Executes add_numbers(20, 30) → "20 + 30 = 50"   │
│  • Step 5: LLM generates final response                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│   LangchainInstrumentor (opentelemetry-instrumentation-     │
│   langchain, Traceloop-based)                               │
│  • Auto-captures agent workflow steps                       │
│  • Creates spans for LLM calls and tool executions          │
│  • Adds Traceloop semantic convention attributes:           │
│    - traceloop.workflow.name: MathTutorAgent                │
│    - traceloop.span.kind: workflow / tool / task            │
│    - traceloop.entity.name: tool_name                       │
│  • Adds LLM semantic convention attributes:                 │
│    - gen_ai.system: openai                                  │
│    - gen_ai.request.model: gpt-4o                           │
│    - gen_ai.completion.0.content: response text             │
│    - gen_ai.completion.0.tool_calls.0.name: tool_name       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│    OpenTelemetry SDK (Transmission via HTTP)                │
│  • Batches spans using BatchSpanProcessor                   │
│  • Sends to OTLP HTTP endpoint (localhost:4318)             │
│  • OTLPSpanExporter (proto/http)                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│   OpenTelemetry Collector (Docker: langchain-test-          │
│   collector)                                                │
│  • Receives OTLP on port 4317 (gRPC) / 4318 (HTTP)         │
│  • transform/gen_ai_conversion processor:                   │
│    - traceloop.workflow.name → gen_ai.agent.name            │
│      (only on workflow spans)                               │
│    - traceloop.entity.name → gen_ai.tool.name               │
│      (only on tool spans)                                   │
│  • Adds service.name=langchain-test, deployment.environment │
│  • Exports traces + metrics + logs to New Relic             │
│  • Logs spans locally for debugging                         │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                     New Relic Platform                      │
│  • AI Monitoring Dashboard                                  │
│  • LLM Token Usage & Cost Tracking                          │
│  • Tool Call Analytics                                      │
│  • Distributed Tracing with Waterfall View                  │
│  • Query by gen_ai.agent.name, gen_ai.tool.name, etc.       │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 Why This Architecture?

- **LangChain**: Agent workflow logic and tool orchestration
- **LangchainInstrumentor**: Auto-instrumentation via Traceloop-based OTel integration
- **OpenTelemetry SDK**: Standard protocol, `BatchSpanProcessor`, OTLP HTTP export
- **OTel Collector**: Vendor-agnostic attribute transformation and routing
- **New Relic**: Observability platform and AI Monitoring visualization

---

## 2. Data Flow Pipeline

1. **Application** (`langchain_app.py`):
   - `ChatOpenAI(model="gpt-4o", temperature=0)` for reasoning
   - Four `@tool` functions: `add_numbers`, `subtract_numbers`, `multiply_numbers`, `divide_numbers`
   - `create_openai_tools_agent` + `AgentExecutor(name="MathTutorAgent")`
   - `LangchainInstrumentor().instrument()` auto-instruments all LangChain operations
   - Manual root span `agent_response` with `gen_ai.output.messages` set as JSON array

2. **OTel SDK**: `BatchSpanProcessor` + `OTLPSpanExporter` → HTTP to `localhost:4318`

3. **OTel Collector** (`langchain-test-collector-config.yaml`):
   - Receives on 4317 (gRPC) and 4318 (HTTP)
   - `transform/gen_ai_conversion` maps Traceloop attributes to Gen AI conventions
   - Exports traces, metrics, and logs to New Relic staging endpoint

4. **New Relic**: Ingests and visualizes telemetry

---

## 3. Application Configuration (langchain_app.py)

### Initialization Order

> ⚠️ `TracerProvider` must be set and `LangchainInstrumentor().instrument()` must be called **before** creating the agent. This ensures all LangChain spans are captured.

```python
import os, json
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

# 1. Load env vars
load_dotenv(find_dotenv(), override=True)

# 2. Set up TracerProvider
prov = TracerProvider()
prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(prov)

# 3. Instrument LangChain
LangchainInstrumentor().instrument()

# 4. Define tools
@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result."""
    return f"{a} + {b} = {a + b}"

# ... subtract_numbers, multiply_numbers, divide_numbers ...

tools = [add_numbers, subtract_numbers, multiply_numbers, divide_numbers]

# 5. Build agent
llm = ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o"), temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful math tutor who can perform calculations using the provided tools. Always show your work and explain the steps clearly."),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, name="MathTutorAgent")

# 6. FastAPI app
app = FastAPI(
    title="LangChain Math Tutor Agent",
    description="Math tutor agent with LangChain tools and OpenTelemetry instrumentation",
)

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

# 7. Endpoint — manually create root span, set gen_ai.output.messages
@app.post("/prompt", response_model=PromptResponse)
async def prompt_agent(request: PromptRequest):
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("agent_response") as span:
        result = await agent_executor.ainvoke({"input": request.prompt})
        output_messages = json.dumps([{
            "role": "assistant",
            "content": result["output"]
        }])
        span.set_attribute("gen_ai.output.messages", output_messages)

    return PromptResponse(response=result["output"])
```

### Tool Definition Pattern

```python
@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result."""
    return f"{a} + {b} = {a + b}"

@tool
def subtract_numbers(a: int, b: int) -> str:
    """Subtract b from a and return the result."""
    return f"{a} - {b} = {a - b}"

@tool
def multiply_numbers(a: int, b: int) -> str:
    """Multiply two numbers together and return the result."""
    return f"{a} * {b} = {a * b}"

@tool
def divide_numbers(a: int, b: int) -> str:
    """Divide a by b and return the result. Returns error if b is zero."""
    if b == 0:
        return "Error: Cannot divide by zero"
    return f"{a} / {b} = {a / b}"
```

The `LangchainInstrumentor` automatically captures for each tool call:
- Tool name from `traceloop.entity.name`
- Input/output in `traceloop.entity.input` / `traceloop.entity.output`

### Required Environment Variables

| Variable | Purpose | Example Value |
|----------|---------|---------------|
| `OPENAI_API_KEY` | OpenAI API authentication | `sk-...` |
| `NEW_RELIC_LICENSE_KEY` | New Relic ingest key (used by collector) | `your-nr-license-key` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel Collector HTTP endpoint | `http://localhost:4318` |
| `OTEL_SERVICE_NAME` | Service name for telemetry | `langchain-test` |
| `LLM_MODEL` | (Optional) Override LLM model | `gpt-4o` |

---

## 4. OpenTelemetry Collector Configuration

### Files

| File | Role |
|------|------|
| `langchain-test-collector-config.yaml` | **Active config** — mounted by Docker Compose into the container |
| `docker-compose-langchain-test.yaml` | Docker Compose definition for the collector |

### Docker Compose (`docker-compose-langchain-test.yaml`)

```yaml
services:
  langchain-test-collector:
    image: otel/opentelemetry-collector-contrib:0.91.0
    container_name: langchain-test-collector
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./langchain-test-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver
      - "55679:55679" # ZPages extension
    env_file:
      - .env
    restart: unless-stopped
    networks:
      - langchain-otel-network

networks:
  langchain-otel-network:
    driver: bridge
```

### Active Config (`langchain-test-collector-config.yaml`)

#### Receivers

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
```

#### Processors

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

  batch:
    timeout: 10s
    send_batch_size: 1024

  resource:
    attributes:
      - key: service.name
        value: langchain-test
        action: upsert
      - key: deployment.environment
        value: development
        action: upsert

  transform/gen_ai_conversion:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          # Set agent name only on workflow spans
          - 'set(attributes["gen_ai.agent.name"], attributes["traceloop.workflow.name"]) where attributes["traceloop.span.kind"] == "workflow"'
          # Set tool name only on tool execution spans
          - 'set(attributes["gen_ai.tool.name"], attributes["traceloop.entity.name"]) where attributes["traceloop.span.kind"] == "tool"'
```

**Why span-kind-aware conditions?**

The `LangchainInstrumentor` sets `traceloop.span.kind` on every span. Using it as a filter ensures:
- `gen_ai.agent.name` is set **only** on the top-level workflow span (not on every LLM call)
- `gen_ai.tool.name` is set **only** on actual tool execution spans (not on LLM or prompt spans)

| Source Attribute | Target Attribute | Condition |
|------------------|------------------|-----------|
| `traceloop.workflow.name` | `gen_ai.agent.name` | `traceloop.span.kind == "workflow"` |
| `traceloop.entity.name` | `gen_ai.tool.name` | `traceloop.span.kind == "tool"` |

#### Exporters

```yaml
exporters:
  otlphttp/newrelic:
    endpoint: https://staging-otlp.nr-data.net:4318
    headers:
      api-key: ${NEW_RELIC_LICENSE_KEY}
    compression: gzip
    timeout: 30s
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s

  logging:
    loglevel: debug

  file:
    path: ./telemetry-data.json  # optional local debug output
```

#### Pipelines

```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource, transform/gen_ai_conversion]
      exporters: [otlphttp/newrelic, logging]

    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource]
      exporters: [otlphttp/newrelic]

    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch, resource]
      exporters: [otlphttp/newrelic]
```

### Enable New Relic AI Monitoring

To surface your app in New Relic's **AI Monitoring** section, add `aiEnabledApp: "true"` to the `resource` processor:

```yaml
processors:
  resource:
    attributes:
      - key: service.name
        value: langchain-test
        action: upsert
      - key: deployment.environment
        value: development
        action: upsert
      - key: aiEnabledApp
        value: "true"
        action: insert
```

> This is required for OTel-instrumented apps. Without it, spans arrive in New Relic but the app will not appear in the AI Monitoring entity list. Apps using the New Relic agent get this automatically.

---

## 5. Semantic Conventions and Attribute Mapping

### Attribute Reference

#### Auto-captured by `LangchainInstrumentor`

| Attribute | Description | Example |
|-----------|-------------|---------|
| `gen_ai.system` | LLM provider | `openai` |
| `gen_ai.request.model` | Requested model | `gpt-4o` |
| `gen_ai.response.model` | Model used in response | `gpt-4o` |
| `gen_ai.request.temperature` | Temperature | `0` |
| `gen_ai.prompt.0.role` | First message role | `system` |
| `gen_ai.prompt.0.content` | System prompt text | `You are a helpful math tutor...` |
| `gen_ai.prompt.1.role` | User message role | `user` |
| `gen_ai.prompt.1.content` | User query | `What is 20 plus 30?` |
| `gen_ai.usage.input_tokens` | Input token count | `172` |
| `gen_ai.usage.output_tokens` | Output token count | `9` |
| `gen_ai.completion.0.content` | LLM response text | `20 plus 30 equals 50.` |
| `gen_ai.completion.0.finish_reason` | Stop reason | `stop` or `tool_calls` |
| `gen_ai.completion.0.tool_calls.0.name` | Tool chosen by LLM | `add_numbers` |
| `gen_ai.completion.0.tool_calls.0.arguments` | Tool args | `{"a": 20, "b": 30}` |
| `traceloop.workflow.name` | Agent/executor name | `MathTutorAgent` |
| `traceloop.span.kind` | Span type | `workflow`, `tool`, `task` |
| `traceloop.entity.name` | Tool name (on tool spans) | `add_numbers` |

#### Set Manually in `langchain_app.py`

| Attribute | Span | Value |
|-----------|------|-------|
| `gen_ai.output.messages` | `agent_response` (root span) | `[{"role": "assistant", "content": "..."}]` (JSON string) |

#### Set by `transform/gen_ai_conversion` Processor

| Attribute | Source | Condition |
|-----------|--------|-----------|
| `gen_ai.agent.name` | `traceloop.workflow.name` | `traceloop.span.kind == "workflow"` |
| `gen_ai.tool.name` | `traceloop.entity.name` | `traceloop.span.kind == "tool"` |

---

## 6. Agent Trace Structure

### Span Tree for "What is 20 plus 30?"

```
Root Span: agent_response  (manually created)
  └── gen_ai.output.messages: [{"role": "assistant", "content": "20 plus 30 equals 50."}]
      │
      ├── Span: MathTutorAgent  (traceloop.span.kind: workflow)
      │     ├── traceloop.workflow.name: MathTutorAgent
      │     └── gen_ai.agent.name: MathTutorAgent  ← set by collector
      │
      ├── Span: ChatPromptTemplate  (traceloop.span.kind: task)
      │     └── Formats system prompt + user input using MessagesPlaceholder
      │
      ├── Span: ChatOpenAI  (LLM Call #1)
      │     ├── gen_ai.system: openai
      │     ├── gen_ai.request.model: gpt-4o
      │     ├── gen_ai.prompt.0.role: system
      │     ├── gen_ai.prompt.1.role: user
      │     ├── gen_ai.prompt.1.content: What is 20 plus 30?
      │     ├── gen_ai.usage.input_tokens: ~172
      │     ├── gen_ai.usage.output_tokens: ~18
      │     ├── gen_ai.completion.0.finish_reason: tool_calls
      │     ├── gen_ai.completion.0.tool_calls.0.name: add_numbers
      │     └── gen_ai.completion.0.tool_calls.0.arguments: {"a": 20, "b": 30}
      │
      ├── Span: add_numbers  (traceloop.span.kind: tool)
      │     ├── traceloop.entity.name: add_numbers
      │     ├── traceloop.workflow.name: MathTutorAgent
      │     └── gen_ai.tool.name: add_numbers  ← set by collector
      │
      └── Span: ChatOpenAI  (LLM Call #2)
            ├── gen_ai.prompt includes tool result: "20 + 30 = 50"
            ├── gen_ai.usage.input_tokens: ~205
            ├── gen_ai.usage.output_tokens: ~9
            ├── gen_ai.completion.0.content: 20 plus 30 equals 50.
            └── gen_ai.completion.0.finish_reason: stop
```

**Total spans:** ~6 (1 root + ~5 auto-instrumented child spans)

### Request / Response Example

**Request:**
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

---

## 7. Running the Application

### Setup

**1. Create virtual environment and install dependencies:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure environment variables:**
```bash
# Create .env from example and fill in your keys
# OPENAI_API_KEY=sk-...
# NEW_RELIC_LICENSE_KEY=...
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# OTEL_SERVICE_NAME=langchain-test
# OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

**3. Start OTel Collector:**
```bash
docker-compose -f docker-compose-langchain-test.yaml up -d
```

**4. Start FastAPI application:**
```bash
uvicorn langchain_app:app --reload --host 0.0.0.0 --port 8000
```

**5. Send a request:**
```bash
curl -X POST http://localhost:8000/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 20 plus 30?"}'
```

**6. View traces in New Relic:**
- Navigate to **APM → Services → langchain-test**
- Open Distributed Tracing to see span waterfall
- Query: `SELECT * FROM Span WHERE gen_ai.agent.name = 'MathTutorAgent'`

---

## 8. Attributes Emitted — Full Reference

### Root Span (`agent_response`)

```
Manually set in prompt_agent():
  → gen_ai.output.messages: [{"role": "assistant", "content": "20 plus 30 equals 50."}]
```

### Workflow Span (`MathTutorAgent`)

```
Auto-captured by LangchainInstrumentor:
  → traceloop.workflow.name: MathTutorAgent
  → traceloop.span.kind: workflow

Set by transform/gen_ai_conversion processor:
  → gen_ai.agent.name: MathTutorAgent
```

### LLM Span #1 (First ChatOpenAI call)

```
Auto-captured by LangchainInstrumentor:
  → gen_ai.system: openai
  → gen_ai.request.model: gpt-4o
  → gen_ai.response.model: gpt-4o
  → gen_ai.request.temperature: 0
  → gen_ai.prompt.0.role: system
  → gen_ai.prompt.0.content: You are a helpful math tutor...
  → gen_ai.prompt.1.role: user
  → gen_ai.prompt.1.content: What is 20 plus 30?
  → gen_ai.usage.input_tokens: ~172
  → gen_ai.usage.output_tokens: ~18
  → gen_ai.completion.0.finish_reason: tool_calls
  → gen_ai.completion.0.tool_calls.0.name: add_numbers
  → gen_ai.completion.0.tool_calls.0.arguments: {"a": 20, "b": 30}
```

### Tool Span (`add_numbers`)

```
Auto-captured by LangchainInstrumentor:
  → traceloop.workflow.name: MathTutorAgent
  → traceloop.entity.name: add_numbers
  → traceloop.span.kind: tool

Set by transform/gen_ai_conversion processor:
  → gen_ai.tool.name: add_numbers
```

### LLM Span #2 (Second ChatOpenAI call)

```
Auto-captured by LangchainInstrumentor:
  → gen_ai.system: openai
  → gen_ai.request.model: gpt-4o
  → gen_ai.response.model: gpt-4o
  → gen_ai.prompt includes tool result: "20 + 30 = 50"
  → gen_ai.usage.input_tokens: ~205
  → gen_ai.usage.output_tokens: ~9
  → gen_ai.completion.0.content: 20 plus 30 equals 50.
  → gen_ai.completion.0.finish_reason: stop
```

---

## 9. Known Limitations

### 9.1 `gen_ai.output.messages` Set Manually

Issue with Response Visibility : While the attribute `gen_ai.completion.0.content` is captured by LangChainInstrumentator, visible in logs/raw span data and properly mapped to gen_ai.output.messages, the response content isn't appearing in the AI Responses table because mapping is failing due to mismatch of data format. This is fixed by manual mapping of response attribute in app.py.The `gen_ai.output.messages` attribute is not auto-captured on the root span. It is manually set in `prompt_agent()` as a JSON array string: `[{"role": "assistant", "content": "..."}]`. This is required for the New Relic AI Responses table to display the response correctly.

The auto-captured `gen_ai.completion.0.content` on child LLM spans contains the same text but is on a different span.

### 9.2 `gen_ai.agent.name` Not Set in App Code

`gen_ai.agent.name` is derived entirely by the OTel Collector from `traceloop.workflow.name`. The agent name `MathTutorAgent` comes from `AgentExecutor(name="MathTutorAgent")` in the app, which Traceloop/LangchainInstrumentor picks up and sets as `traceloop.workflow.name`.

### 9.3 Multiple Tool Calls

Only the first tool call is surfaced in `gen_ai.completion.0.tool_calls.0.name`. For multi-tool workflows, full data is visible in the trace waterfall view.

Manual mapping is required for mapping agent name and tool name, can be found in config file.

---

## 10. Debugging Tips

```bash
# Stream all collector logs
docker logs langchain-test-collector -f

# Check gen_ai and traceloop attributes are flowing
docker logs langchain-test-collector 2>&1 | grep "gen_ai\.\|traceloop\."

# Verify agent name is being set on workflow spans
docker logs langchain-test-collector 2>&1 | grep "gen_ai.agent.name"

# Verify tool name is being set on tool spans
docker logs langchain-test-collector 2>&1 | grep "gen_ai.tool.name"

# Verify output messages are on root span
docker logs langchain-test-collector 2>&1 | grep "gen_ai.output.messages"

# Check export status to New Relic
docker logs langchain-test-collector 2>&1 | grep "TracesExporter"
```

### Common Issues

| Issue | Solution |
|-------|----------|
| No spans appearing | Check collector is running and port 4318 is reachable |
| `gen_ai.agent.name` missing | Verify `traceloop.span.kind == "workflow"` exists; check transform processor is active |
| `gen_ai.tool.name` missing | Verify `traceloop.span.kind == "tool"` exists on tool spans |
| `gen_ai.output.messages` not in NR UI | Confirm value is a JSON array string, not a plain string |
| New Relic not receiving data | Verify `NEW_RELIC_LICENSE_KEY` and staging endpoint are correct |
| SSL error on macOS | `urllib3<2` is pinned in `requirements.txt` to fix LibreSSL 2.8.3 incompatibility |

---

## 11. Resources

- [LangChain Documentation](https://python.langchain.com/)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/instrumentation/python/)
- [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [OTel Collector Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor)
- [New Relic AI Monitoring](https://docs.newrelic.com/docs/ai-monitoring/)
