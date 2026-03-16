# Strands Agents Math Tutor with OpenTelemetry and New Relic Integration

**Project:** Strands-sample-app
**Dependencies:**
- Python: 3.12
- OpenTelemetry SDK: Latest
- strands-agents: Latest (with OpenAI support)
- FastAPI: Latest
- python-dotenv: Latest
- OpenTelemetry Collector: 0.91.0

**Table of Contents:**
1. [Technology Stack Overview](#1-technology-stack-overview) — architecture, data flow, Strands Agents framework
2. [Application Configuration](#2-application-configuration) — setup code, environment variables, tools
3. [OTel Collector Configuration](#3-opentelemetry-collector-configuration) — transformation pipeline, latest conventions, AI Monitoring setup
4. [Strands Agent Telemetry](#4-strands-agent-telemetry--span-structure-and-attributes) — native attributes, span structure
5. [Running the Application](#5-running-the-application) — setup, testing, verification
6. [Known Limitations](#6-known-limitations) — advantages of latest conventions
7. [Production Deployment](#7-production-deployment-considerations) — deployment guide
8. [Troubleshooting](#8-troubleshooting) — common issues and fixes
9. [Latest Semantic Conventions](#9-latest-semantic-conventions-recommended) — detailed reference


## 1. Technology Stack Overview

### 1.1 What is Strands Agents?

**Strands Agents** is a framework for building AI agents that provides:

- **Agents**: Autonomous agents that use LLMs to reason, plan, and decide which tools to call in an event loop
- **Tools**: Python functions decorated with `@tool` that agents can invoke to perform specific tasks
- **Built-in Telemetry**: Native OpenTelemetry instrumentation via `StrandsTelemetry` — no external instrumentor library needed
- **Model Flexibility**: Support for multiple model providers (OpenAI, Bedrock, etc.) via pluggable model classes

### 1.2 High-Level Architecture

This sample application brings together multiple technologies in a cohesive observability pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                    USER REQUEST                             │
│              "What is 2 + 2 and multiply by 9?"             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Application (strands_app.py)            │
│  • Receives HTTP request at /prompt endpoint                │
│  • Routes prompt to Strands Agent                           │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│               Strands Agent (Event Loop)                    │
│  • Cycle 1: LLM decides to call add_numbers(2, 2) → 4      │
│  • Cycle 2: LLM decides to call multiply_numbers(4, 9) → 36│
│  • Cycle 3: LLM generates final response                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│          StrandsTelemetry (Built-in OTel)                   │
│  • Auto-captures agent event loop cycles                    │
│  • Creates spans for chat (LLM) and execute_tool operations │
│  • Emits gen_ai.* semantic convention attributes natively   │
│  • Records span events for messages and tool calls          │
│                                                             │
│  Two telemetry modes:                                       │
│  ┌───────────────────────┐  ┌────────────────────────────┐  │
│  │ Default               │  │ Latest (Recommended)       │  │
│  │ Per-event messages     │  │ Consolidated messages      │  │
│  │ (gen_ai.user.message,  │  │ (gen_ai.client.inference.  │  │
│  │  gen_ai.choice, etc.)  │  │  operation.details)        │  │
│  └───────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│      OpenTelemetry Collector (Transformation)               │
│  • Receives OTLP traces on port 4318                        │
│  • Transforms span events → span attributes                 │
│  • Batches spans for efficient export                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
              ┌────────────┴────────────┐
              ↓                         ↓
┌──────────────────────┐   ┌──────────────────────┐
│   New Relic          │   │   Debug/File Output  │
└──────────────────────┘   └──────────────────────┘
```

### 1.3 Data Flow Pipeline

1. **Application (Instrumentation)**: The Strands `Agent` with `StrandsTelemetry` automatically traces:
   - Agent event loop cycles (`execute_event_loop_cycle` spans)
   - LLM chat calls (`chat` spans with gen_ai.* attributes)
   - Tool invocations (`execute_tool` spans with tool metadata)
   - Message history as consolidated span events (`gen_ai.client.inference.operation.details`)

2. **OTel SDK (Transmission)**: Exports OTLP data with latest GenAI semantic conventions to the OpenTelemetry Collector at `http://localhost:4318/v1/traces`

3. **OTel Collector (Transformation & Routing)**: Receives traces, transforms consolidated span events into span attributes, maps `gen_ai.provider.name` to `gen_ai.system` for New Relic compatibility, batches spans, and exports to configured destinations

4. **Observability Platforms**:
   - **New Relic**: Receives and visualizes complete telemetry data
   - **Local File**: Optional JSON export for debugging (`telemetry-data.json`)
   - **Console Logs**: Debug output via `logging` exporter

### 1.4 Key Differences from Other Frameworks

**Compared to LlamaIndex:**
- Strands Agents emits **OTel GenAI semantic conventions natively** via its built-in `StrandsTelemetry`
- No external instrumentor library is needed
- Attributes like `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.*` are emitted directly
- The OTel Collector only needs to transform **span events into span attributes** (not remap attribute names)

**This Implementation's Approach:**
- Uses latest semantic conventions (`OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`)
- Consolidates all messages into a single `gen_ai.client.inference.operation.details` span event
- Pre-serializes `gen_ai.input.messages` and `gen_ai.output.messages` as JSON strings
- Preserves complete conversation history (user, assistant, tool messages)
- Simpler collector transformation pipeline

---

## 2. Application Configuration

### 2.1 Setup Overview

Strands Agents makes setup straightforward — there is no critical initialization order. The telemetry is configured via `StrandsTelemetry` and the agent is created with a model, tools, and system prompt. See [strands_app.py](strands_app.py) for the complete implementation.

**Key Setup Steps:**

```python
from strands import Agent, tool
from strands.telemetry import StrandsTelemetry
from strands.models.openai import OpenAIModel
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# 1. Load environment variables
load_dotenv(find_dotenv(), override=True)

# 2. Define tools using @tool decorator
@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result.

    Args:
        a: The first number.
        b: The second number.
    """
    return f"{a} + {b} = {a + b}"

@tool
def multiply_numbers(a: int, b: int) -> str:
    """Multiply two numbers together and return the result.

    Args:
        a: The first number.
        b: The second number.
    """
    return f"{a} * {b} = {a * b}"

# 3. Set up telemetry (OTLP exporter + metrics)
strands_telemetry = StrandsTelemetry()
strands_telemetry.setup_otlp_exporter(endpoint="http://localhost:4318/v1/traces")
strands_telemetry.setup_meter(
    enable_console_exporter=False,
    enable_otlp_exporter=True,
)

# 4. Initialize FastAPI app
app = FastAPI(
    title="Strands Math Tutor Agent",
    description="Math tutor agent with Strands tools and OpenTelemetry instrumentation",
)

# 5. Create agent with model, system prompt, and tools
openai_model = OpenAIModel(model_id="gpt-4o")

agent = Agent(
    model=openai_model,
    system_prompt="You are a helpful math tutor who can perform calculations using the provided tools.",
    tools=[add_numbers, subtract_numbers, multiply_numbers, divide_numbers],
)

# 6. Define API endpoint to invoke the agent
@app.post("/prompt")
async def prompt_agent(request: PromptRequest):
    response = agent(request.prompt)
    return PromptResponse(response=str(response))
```

### 2.2 Required Environment Variables

| Variable | Purpose | Required | Example Value |
|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI API authentication key | Yes | `sk-your-openai-api-key-here` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTel Collector endpoint | No | `http://localhost:4318` |
| `OTEL_SERVICE_NAME` | Service name for telemetry | No | `strands-math-tutor` |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | Enable latest GenAI conventions | Yes (recommended) | `gen_ai_latest_experimental` |
| `NEW_RELIC_LICENSE_KEY` | New Relic license key (OTel Collector) | No (if not exporting to NR) | `your-new-relic-license-key-here` |

**Critical Note:** This implementation uses `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` which is **required** to preserve complete conversation history. The application connects to `http://localhost:4318/v1/traces` by default.

### 2.3 Key Implementation Points

- **Tool Definition:** Use the `@tool` decorator on Python functions with docstrings (docstrings become tool descriptions and arg descriptions are extracted from the `Args` section)
- **Telemetry:** Create a `StrandsTelemetry()` instance and call `setup_otlp_exporter()` and `setup_meter()` — no external instrumentor needed
- **Model Configuration:** Use `OpenAIModel(model_id="gpt-4o")` for OpenAI models
- **Agent Creation:** `Agent(model=..., system_prompt=..., tools=[...])` — the agent runs an event loop that calls the LLM and executes tools automatically
- **Invocation:** Simply call `agent("your prompt")` — the agent handles the full reasoning loop
- **Web Framework:** FastAPI wraps the agent in a REST API with a `POST /prompt` endpoint, making it accessible over HTTP
- **Latest Conventions:** Ensure `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set to enable consolidated message telemetry

### 2.4 Available Tools in This Implementation

The Math Tutor Agent has four tools available:

1. **`add_numbers(a: int, b: int)`** — Adds two integers and returns the result (e.g., "2 + 3 = 5")
   - Tool call: `add_numbers(2, 3)`
   - Response: `"2 + 3 = 5"`

2. **`subtract_numbers(a: int, b: int)`** — Subtracts b from a and returns the result (e.g., "10 - 3 = 7")
   - Tool call: `subtract_numbers(10, 3)`
   - Response: `"10 - 3 = 7"`

3. **`multiply_numbers(a: int, b: int)`** — Multiplies two integers and returns the result (e.g., "4 * 5 = 20")
   - Tool call: `multiply_numbers(4, 5)`
   - Response: `"4 * 5 = 20"`

4. **`divide_numbers(a: int, b: int)`** — Divides a by b and returns the result; returns an error if b is zero
   - Tool call: `divide_numbers(10, 2)`
   - Response: `"10 / 2 = 5.0"`
   - Error case: `divide_numbers(10, 0)` returns `"Error: Cannot divide by zero"`

Each tool is defined in [strands_app.py:14-57](strands_app.py#L14-L57) with proper docstrings that the agent uses to understand their purpose and parameters.

---

## 3. OpenTelemetry Collector Configuration

The OTel Collector receives OTLP traces from Strands Agents and **transforms consolidated span events into span attributes** so that observability platforms can properly parse complete input/output messages. This implementation uses the latest semantic conventions for best data fidelity.

See [strands-otel-collector-config.yaml](strands-otel-collector-config.yaml) for the complete configuration.

### 3.1 Key Components

**Receivers:**
- OTLP gRPC on port 4317
- OTLP HTTP on port 4318 (used by the application)

**Processors (in order):**
1. `memory_limiter` — Prevents OOM (512 MiB limit, 1s check interval)
2. `batch` — Groups spans (1024 batch size, 10s timeout)
3. `resource` — Adds/updates service attributes:
   - `service.name`: `strands-math-tutor`
   - `deployment.environment`: `development`
   - `aiEnabledApp`: `"true"` — **required** to surface the app in New Relic AI Monitoring (see [3.5](#35-enable-new-relic-ai-monitoring))
4. `transform/gen_ai_conversion` — Extracts Gen AI semantic conventions from span events to span attributes:
   - Copies `gen_ai.input.messages` from `gen_ai.client.inference.operation.details` events
   - Copies `gen_ai.output.messages` from span events
   - Extracts `gen_ai.response.finish_reasons` from `finish_reason` in output messages
   - Maps `gen_ai.provider.name` to `gen_ai.system` (for New Relic compatibility)

**Exporters:**
- `otlphttp/newrelic` — Sends to New Relic staging endpoint (`staging-otlp.nr-data.net:4318`)
- `logging` — Prints to collector stdout (debug output, info level)
- `file` — Writes telemetry data to `./telemetry-data.json` (for local inspection)

### 3.2 Pipelines

| Pipeline | Receivers | Processors | Exporters |
|----------|-----------|-----------|-----------|
| Traces | OTLP | memory_limiter, batch, resource, transform/gen_ai_conversion | otlphttp/newrelic, logging, file |
| Metrics | OTLP | memory_limiter, batch, resource | otlphttp/newrelic |
| Logs | OTLP | memory_limiter, batch, resource | otlphttp/newrelic |

### 3.3 Transformation Details (Latest Semantic Conventions)

The `transform/gen_ai_conversion` processor uses OTTL (OpenTelemetry Transformation Language) to handle the latest GenAI semantic conventions (when `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set):

1. **Extract `gen_ai.input.messages`** from span events (`gen_ai.client.inference.operation.details`)
   - Contains the complete user prompt/request
   - Pre-serialized as JSON string

2. **Extract `gen_ai.output.messages`** from span events
   - Contains the complete LLM response/output
   - Pre-serialized as JSON string with `finish_reason`

3. **Extract `gen_ai.response.finish_reasons`** from span event attributes
   - Captures LLM completion reason: `end_turn` or `tool_use`
   - Parsed from the serialized output messages

4. **Map `gen_ai.provider.name` to `gen_ai.system`** for New Relic compatibility
   - Maps latest convention attribute names to legacy names
   - Ensures New Relic can properly parse the telemetry

This approach preserves the complete conversation history and ensures New Relic can properly parse and display AI agent telemetry data.

### 3.4 Before and After Transformation Comparison

This section shows actual span attributes as emitted by Strands and after processing by the OTel Collector, demonstrating how the transformer enriches traces with consolidated message data.

#### 1. Chat Span (LLM Call)

**BEFORE Transformation (as emitted by Strands with `gen_ai_latest_experimental`):**

```
Span: chat
    Name           : chat
    Kind           : Internal

Attributes (already gen_ai.* native):
     -> gen_ai.event.start_time: Str(2026-02-20T06:12:12.447929+00:00)
     -> gen_ai.operation.name: Str(chat)
     -> gen_ai.provider.name: Str(strands-agents)
     -> gen_ai.request.model: Str(gpt-4o)
     -> gen_ai.event.end_time: Str(2026-02-20T06:12:14.527613+00:00)
     -> gen_ai.usage.prompt_tokens: Int(455)
     -> gen_ai.usage.input_tokens: Int(455)
     -> gen_ai.usage.completion_tokens: Int(61)
     -> gen_ai.usage.output_tokens: Int(61)
     -> gen_ai.usage.total_tokens: Int(516)
     -> gen_ai.server.time_to_first_token: Int(945)

Events (message history):
     SpanEvent: gen_ai.client.inference.operation.details
         ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":"What is 15 multiplied by 7?"}]}]
         ├── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"I'll use the multiply_numbers tool."}],"finish_reason":"tool_use"}]
```

**AFTER Transformation (OTel Collector Output):**

```
Span: chat
    Name           : chat
    Kind           : Internal

Existing Attributes (unchanged):
     -> gen_ai.operation.name: Str(chat)
     -> gen_ai.system: Str(strands-agents)                        # Mapped from gen_ai.provider.name
     -> gen_ai.request.model: Str(gpt-4o)
     -> gen_ai.usage.input_tokens: Int(455)
     -> gen_ai.usage.output_tokens: Int(61)
     -> gen_ai.usage.total_tokens: Int(516)
     -> gen_ai.server.time_to_first_token: Int(945)

Added by Collector (from span events):
     -> gen_ai.input.messages: Str([{"role":"user","parts":[{"type":"text","content":"What is 15 multiplied by 7?"}]}])
     -> gen_ai.output.messages: Str([{"role":"assistant","parts":[{"type":"text","content":"I'll use the multiply_numbers tool."}],"finish_reason":"tool_use"}])
     -> gen_ai.response.finish_reasons: Slice(["tool_use"])
```

#### 2. Tool Execution Span (multiply_numbers)

**BEFORE Transformation (as emitted by Strands):**

```
Span: execute_tool multiply_numbers
    Name           : execute_tool multiply_numbers
    Kind           : Internal
    Status code    : Ok

Attributes (already gen_ai.* native):
     -> gen_ai.operation.name: Str(execute_tool)
     -> gen_ai.provider.name: Str(strands-agents)
     -> gen_ai.tool.name: Str(multiply_numbers)
     -> gen_ai.tool.call.id: Str(call_wpFGpymEc5OWlAASpuph3ysA)
     -> gen_ai.tool.description: Str(Multiply two numbers together and return the result.)
     -> gen_ai.tool.json_schema: Str({"type":"object","properties":{"a":{"type":"integer","description":"The first number."},"b":{"type":"integer","description":"The second number."}}, ...})
     -> gen_ai.tool.status: Str(success)

Events:
     SpanEvent: gen_ai.client.inference.operation.details
         ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":""}]}]
         └── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"15 * 7 = 105"}],"finish_reason":"end_turn"}]
```

**AFTER Transformation (OTel Collector Output):**

```
Span: execute_tool multiply_numbers
    Name           : execute_tool multiply_numbers
    Kind           : Internal
    Status code    : Ok

Existing Attributes (unchanged):
     -> gen_ai.operation.name: Str(execute_tool)
     -> gen_ai.system: Str(strands-agents)                        # Mapped from gen_ai.provider.name
     -> gen_ai.tool.name: Str(multiply_numbers)
     -> gen_ai.tool.call.id: Str(call_wpFGpymEc5OWlAASpuph3ysA)
     -> gen_ai.tool.description: Str(Multiply two numbers together and return the result.)
     -> gen_ai.tool.json_schema: Str({"type":"object","properties":{"a":{"type":"integer","description":"The first number."},"b":{"type":"integer","description":"The second number."}}, ...})
     -> gen_ai.tool.status: Str(success)

Added by Collector (from span events):
     -> gen_ai.input.messages: Str([{"role":"user","parts":[{"type":"text","content":""}]}])
     -> gen_ai.output.messages: Str([{"role":"assistant","parts":[{"type":"text","content":"15 * 7 = 105"}],"finish_reason":"end_turn"}])
     -> gen_ai.response.finish_reasons: Slice(["end_turn"])
```

#### 3. Event Loop Cycle Span

**No Transformation Needed** — The cycle span passes through unchanged:

```
Span: execute_event_loop_cycle
    Name           : execute_event_loop_cycle
    Kind           : Internal

Attributes:
     -> gen_ai.event.start_time: Str(2026-02-20T06:12:14.545780+00:00)
     -> event_loop.cycle_id: Str(e25dc6ff-d5d1-4565-a413-fafbae88f196)
     -> event_loop.parent_cycle_id: Str(6dff8f0f-e062-4dd5-9e12-afcaa6a2f42b)
     -> gen_ai.event.end_time: Str(2026-02-20T06:12:15.966113+00:00)
```

#### Transformation Summary

The OTel Collector applies the `transform/gen_ai_conversion` processor with two main operations:

1. **Extract from Events**: Copies pre-serialized messages from span events to span attributes
   - `gen_ai.client.inference.operation.details` event → `gen_ai.input.messages` and `gen_ai.output.messages` span attributes
   - Extracts `finish_reason` from the JSON output messages

2. **Provider Name Mapping**: Maps attribute names for platform compatibility
   - `gen_ai.provider.name` → `gen_ai.system` (for New Relic compatibility)
   - Only applies if `gen_ai.system` is not already present

**Key Advantage**: Since Strands emits with `gen_ai_latest_experimental`, messages are already consolidated and pre-serialized. The collector simply needs to copy them to the span level, making the transformation simple and preserving data fidelity.

### 3.5 Enable New Relic AI Monitoring

To surface your app in New Relic's **AI Monitoring** section, add `aiEnabledApp: "true"` to the `resource` processor in [`strands-otel-collector-config.yaml`](./nr-config/strands-otel-collector-config.yaml):

```yaml
processors:
  resource:
    attributes:
      - key: service.name
        value: strands-math-tutor
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

## 4. Strands Agent Telemetry — Span Structure and Attributes

### 4.1 Native gen_ai.* Attributes

Strands Agents emits OTel GenAI semantic conventions directly. No collector-side attribute remapping is required for these:

| Attribute | Source | Example Value |
|-----------|--------|---------------|
| `gen_ai.system` | Built-in | `strands-agents` |
| `gen_ai.operation.name` | Built-in | `chat`, `execute_tool` |
| `gen_ai.request.model` | From model config | `gpt-4o` |
| `gen_ai.usage.input_tokens` | From LLM response | `455` |
| `gen_ai.usage.output_tokens` | From LLM response | `61` |
| `gen_ai.usage.prompt_tokens` | From LLM response | `455` |
| `gen_ai.usage.completion_tokens` | From LLM response | `61` |
| `gen_ai.usage.total_tokens` | Computed | `516` |
| `gen_ai.server.time_to_first_token` | Measured | `945` (ms) |
| `gen_ai.tool.name` | From tool decorator | `multiply_numbers` |
| `gen_ai.tool.call.id` | From LLM response | `call_wpFGpymEc5OWlAASpuph3ysA` |
| `gen_ai.tool.description` | From tool docstring | `Multiply two numbers together and return the result.` |
| `gen_ai.tool.json_schema` | From tool signature | `{"properties": {"a": {...}, "b": {...}}, ...}` |
| `gen_ai.tool.status` | From execution | `success` |
| `event_loop.cycle_id` | Built-in | UUID |
| `event_loop.parent_cycle_id` | Built-in | UUID |

### 4.2 Span Events

Strands records detailed message history as **span events** rather than span attributes. The OTel Collector transforms these into span attributes for platform compatibility.

| Event Name | Description | Key Attributes |
|------------|-------------|----------------|
| `gen_ai.user.message` | User input message | `content`: message text |
| `gen_ai.assistant.message` | LLM response (may include tool calls) | `content`: response with text and toolUse objects |
| `gen_ai.tool.message` | Tool input (on tool spans) or tool result (on chat spans) | `content`: tool arguments or result, `role`, `id` |
| `gen_ai.choice` | Final LLM choice for the span | `message`: response text, `finish_reason`: `end_turn` or `tool_use` |

### 4.3 Agent Trace Structure

Strands Agents creates a hierarchical span structure based on its event loop architecture:

#### Span Types

| Span Name | Operation | Description |
|-----------|-----------|-------------|
| `chat` | `gen_ai.operation.name: chat` | An LLM API call. Contains token usage, model info, and message events |
| `execute_tool <name>` | `gen_ai.operation.name: execute_tool` | A tool execution. Contains tool metadata, input arguments, and result |
| `execute_event_loop_cycle` | Event loop orchestration | One iteration of the agent loop (contains a `chat` span and optionally `execute_tool` spans) |

#### Example: "What is 2 + 2 and the answer multiply by 9?"

```
Root Trace: 67f461f2853102a53caaf36539a8bb06
│
├── execute_event_loop_cycle (Cycle 1 - initial)
│   ├── chat (LLM Call #1)
│   │   ├── gen_ai.system: strands-agents
│   │   ├── gen_ai.request.model: gpt-4o
│   │   ├── gen_ai.usage.input_tokens: 455
│   │   ├── gen_ai.usage.output_tokens: 61
│   │   ├── gen_ai.usage.total_tokens: 516
│   │   ├── gen_ai.server.time_to_first_token: 945ms
│   │   │
│   │   ├── Events:
│   │   │   └── gen_ai.client.inference.operation.details
│   │   │       ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":"What is 2 + 2 and the answer multiply by 9?"}]}]
│   │   │       └── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"I'll help you calculate this..."}],"finish_reason":"tool_use"}]
│   │   │
│   │   └── Output: LLM decides to call add_numbers(a=2, b=2)
│   │
│   └── execute_tool add_numbers
│       ├── gen_ai.tool.name: add_numbers
│       ├── gen_ai.tool.call.id: call_wpFGpymEc5OWlAASpuph3ysA
│       ├── gen_ai.tool.description: "Add two numbers together and return the result."
│       ├── gen_ai.tool.status: success
│       └── Result: "2 + 2 = 4"
│
├── execute_event_loop_cycle (Cycle 2 - tool result + next LLM call)
│   ├── chat (LLM Call #2)
│   │   ├── gen_ai.usage.input_tokens: 534
│   │   ├── gen_ai.usage.output_tokens: 43
│   │   ├── gen_ai.usage.total_tokens: 577
│   │   ├── gen_ai.server.time_to_first_token: 661ms
│   │   │
│   │   └── Output: LLM decides to call multiply_numbers(a=4, b=9)
│   │
│   └── execute_tool multiply_numbers
│       ├── gen_ai.tool.name: multiply_numbers
│       ├── gen_ai.tool.call.id: call_9Dnz9Knqq7BaiGblY588i3iM
│       ├── gen_ai.tool.description: "Multiply two numbers together and return the result."
│       ├── gen_ai.tool.status: success
│       └── Result: "4 * 9 = 36"
│
└── execute_event_loop_cycle (Cycle 3 - final response)
    └── chat (LLM Call #3)
        ├── gen_ai.usage.input_tokens: 595
        ├── gen_ai.usage.output_tokens: 32
        ├── gen_ai.usage.total_tokens: 627
        ├── gen_ai.server.time_to_first_token: 1381ms
        ├── gen_ai.response.finish_reasons: ["end_turn"]
        │
        └── Output: "The result of multiplying 4 by 9 is 36. Therefore, (2 + 2) × 9 = 36."
```

**Key Observations:**
1. **3 event loop cycles** — one per LLM reasoning step (tool call → tool call → final answer)
2. **3 chat spans** — each representing one LLM API call with full token usage
3. **2 execute_tool spans** — `add_numbers` and `multiply_numbers`, each with status `success`
4. **Consolidated events** — each chat span carries complete conversation context in `gen_ai.client.inference.operation.details`
5. **Token usage tracked per call** — 455 + 534 + 595 = 1,584 total input tokens
6. **Time-to-first-token** measured per LLM call: 945ms, 661ms, 1381ms
7. **All attributes** use native `gen_ai.*` semantic conventions with latest conventions

---

## 5. Running the Application

### 5.1 Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.12+ | Application runtime |
| pip | Latest | Dependency management |
| Docker | 20.10+ | Running the OTel Collector container |
| Docker Compose | v2+ | Orchestrating the collector service |
| OpenAI API key | — | GPT-4o model access |
| New Relic license | — | Telemetry data export (optional) |

### 5.2 Local Development Setup

#### 1. Clone the repository

```bash
git clone <repository-url>
cd Strands-sample-app
```

#### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows
```

#### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs:

| Package | Role |
|---------|------|
| `strands-agents[openai]` | Strands agent framework with OpenAI model |
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `pydantic` | Request/response validation |
| `python-dotenv` | Loads `.env` into environment |

#### 4. Set up environment variables

Create a `.env` file in the project root:

```env
# OpenAI — required for the LLM agent
OPENAI_API_KEY=<your-openai-api-key>

# New Relic — required if exporting telemetry to New Relic
NEW_RELIC_LICENSE_KEY=<your-new-relic-license-key>
```

**Security note:** Never commit your `.env` file to version control. Add it to `.gitignore`.

### 5.3 Start the OTel Collector

```bash
docker compose -f docker-compose-strands.yaml up -d
```

### Verify the collector is running

```bash
docker ps --filter name=strands-otel-collector
```

You should see the container with status `Up` and ports `4317`, `4318`, and `55679` mapped.

### Stop the collector

```bash
docker compose -f docker-compose-strands.yaml down
```

### Collector ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 4317 | gRPC | OTLP gRPC receiver |
| 4318 | HTTP | OTLP HTTP receiver (used by app) |
| 55679 | HTTP | ZPages debugging UI |

### 5.4 Run the Application

#### Development mode (with auto-reload)

```bash
uvicorn strands_app:app --reload
```

The server starts at `http://localhost:8000`.

#### Custom host and port

```bash
uvicorn strands_app:app --host 0.0.0.0 --port 9000 --reload
```

#### Production mode (multiple workers)

```bash
uvicorn strands_app:app --host 0.0.0.0 --port 8000 --workers 4
```

**Note:** When using multiple workers, each worker creates its own agent instance. Ensure your OpenAI API key has sufficient rate limits.

### 5.5 Verifying the Setup

#### 1. Health check

```bash
curl http://localhost:8000/
```

#### 2. Send a test prompt

```bash
curl -X POST http://localhost:8000/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 15 multiplied by 7?"}'
```

Expected response:

```json
{
  "response": "15 * 7 = 105\n\nThe result of multiplying 15 by 7 is **105**."
}
```

**Available tools in the agent:**
- `add_numbers(a, b)` — Adds two numbers
- `subtract_numbers(a, b)` — Subtracts b from a
- `multiply_numbers(a, b)` — Multiplies two numbers
- `divide_numbers(a, b)` — Divides a by b (returns error for division by zero)

#### 3. Check interactive API docs

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser for Swagger UI.

#### 4. Verify telemetry is flowing

Check the OTel Collector logs:

```bash
docker logs strands-otel-collector --tail 50
```

You should see log lines indicating spans are being received and exported.

To inspect the ZPages debug UI, visit [http://localhost:55679/debug/tracez](http://localhost:55679/debug/tracez).

---

## 6. Known Limitations

### 6.1 Latest Semantic Conventions (Recommended Approach)

**Advantage**: By setting `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, the Strands SDK emits pre-serialized `gen_ai.input.messages` and `gen_ai.output.messages` as consolidated span event attributes.

**Benefits**:
- Complete conversation history is preserved (no loss of intermediate messages)
- Tool calls and their results are properly tracked
- JSON is pre-serialized cleanly (no double-escaping)
- Simpler collector transformation pipeline
- Better data fidelity in observability platforms

**Implementation Details**:
- The SDK consolidates all messages into a single `gen_ai.client.inference.operation.details` span event
- Input and output messages are pre-formatted as JSON strings
- The collector simply copies these attributes to the span level
- New Relic correctly displays the complete conversation and token usage

### `finish_reason` Extraction Requires Regex Parsing (OTTL Has No JSON Parser)

**Limitation**: OTTL (the OTel Collector's transformation language) cannot natively parse JSON strings. Since `gen_ai.output.messages` is emitted as a pre-serialized JSON string, extracting `finish_reason` from it requires a multi-step regex workaround.

**Details**: The `transform/gen_ai_conversion` processor uses three OTTL statements:

```yaml
# Step 1 — Copy the full output messages JSON into the finish_reasons attribute
- 'set(span.attributes["gen_ai.response.finish_reasons"], attributes["gen_ai.output.messages"])
   where name == "gen_ai.client.inference.operation.details"
   and IsMatch(attributes["gen_ai.output.messages"], ".*finish_reason.*")'

# Step 2 — Strip everything before the finish_reason value
- 'replace_pattern(span.attributes["gen_ai.response.finish_reasons"],
   "^[\\s\\S]*\"finish_reason\":\\s*\"", "")
   where name == "gen_ai.client.inference.operation.details"
   and span.attributes["gen_ai.response.finish_reasons"] != nil'

# Step 3 — Strip everything after the finish_reason value
- 'replace_pattern(span.attributes["gen_ai.response.finish_reasons"],
   "\"[\\s\\S]*$", "")
   where name == "gen_ai.client.inference.operation.details"
   and span.attributes["gen_ai.response.finish_reasons"] != nil'
```

The result is a plain string value such as `end_turn` or `tool_use` stored in `gen_ai.response.finish_reasons`.

**Why regex is unavoidable**: OTTL has no `json_parse()` or key-access function for string-encoded JSON. The regex strips everything before and after the `finish_reason` value — it is the only available approach in the collector today.

**Risks**:
- If the JSON structure of `gen_ai.output.messages` changes between Strands SDK versions, the patterns may silently produce incorrect values
- If a message body contains the literal string `"finish_reason":`, the regex may match the wrong occurrence
- The full `gen_ai.output.messages` attribute is unaffected and remains intact

### 6.2 `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` Is Required

**Limitation**: The collector configuration **only works correctly** when `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set in `.env`. Without it, none of `gen_ai.input.messages`, `gen_ai.output.messages`, or `gen_ai.response.finish_reasons` will be populated on any span.

**Details**: The `transform/gen_ai_conversion` processor targets the `gen_ai.client.inference.operation.details` span event:

```yaml
- context: spanevent
  statements:
    - 'set(span.attributes["gen_ai.input.messages"], attributes["gen_ai.input.messages"])
       where name == "gen_ai.client.inference.operation.details"'
    - 'set(span.attributes["gen_ai.output.messages"], attributes["gen_ai.output.messages"])
       where name == "gen_ai.client.inference.operation.details"'
```

This event is **only emitted** when the latest GenAI conventions are opted into. Without the env var, the SDK emits individual `gen_ai.user.message`, `gen_ai.assistant.message`, and `gen_ai.choice` events instead — none of which match the processor's condition.

**Required setting in `.env`**:
```
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

**Impact if omitted**: Traces still arrive in New Relic with token usage, model name, and tool metadata — but all input/output message content will be missing from span attributes.

---

## 7. Production Deployment Considerations

### 7.1 Application

- Use `uvicorn` with multiple `--workers` or deploy behind Gunicorn:
  ```bash
  gunicorn strands_app:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
  ```
- Place behind a reverse proxy (nginx, Caddy, or a cloud load balancer) for TLS termination
- Set `--reload` only in development; omit it in production

### 7.2 Environment variables

- Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.) instead of a `.env` file
- Rotate API keys regularly

### 7.3 OTel Collector

- Pin the collector image to a specific version (currently `0.91.0`)
- Tune `memory_limiter` and `batch` settings based on traffic volume
- Update the New Relic endpoint from staging (`staging-otlp.nr-data.net`) to production (`otlp.nr-data.net`)
- Add health checks to the Docker Compose service:
  ```yaml
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:13133/"]
    interval: 30s
    timeout: 5s
    retries: 3
  ```

### 7.4 Containerizing the application

Example `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY strands_app.py .

EXPOSE 8000
CMD ["uvicorn", "strands_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

Add the app service to `docker-compose-strands.yaml` to run everything together:

```yaml
services:
  math-tutor:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      - strands-otel-collector
    networks:
      - strands-otel-network
```

---

## 8. Troubleshooting

### 8.1 Application won't start

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: strands` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `ModuleNotFoundError: fastapi` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `OPENAI_API_KEY not set` | Missing `.env` or env var | Create `.env` with your OpenAI API key |
| `Connection refused on port 4318` | OTel Collector not running | Run `docker compose -f docker-compose-strands.yaml up -d` |
| `Address already in use :8000` | Uvicorn already running | Kill the process: `lsof -i :8000` and `kill -9 <PID>` |

### 8.2 API endpoint not responding

| Symptom | Cause | Fix |
|---------|-------|-----|
| `404 Not Found` on `/prompt` | Route not defined | Verify `strands_app.py` has the `@app.post("/prompt")` endpoint |
| `405 Method Not Allowed` | Wrong HTTP method used | Use `POST`, not `GET` (e.g., `curl -X POST ...`) |
| `422 Unprocessable Entity` | Invalid JSON payload | Ensure payload is valid JSON with `"prompt"` key |

### 8.3 Telemetry not appearing in New Relic

1. **Check collector logs:** `docker logs strands-otel-collector --tail 100`
2. **Verify the license key:** Ensure `NEW_RELIC_LICENSE_KEY` is set in `.env` and correct
3. **Verify network connectivity:** From the collector container, test: `docker exec strands-otel-collector curl -I https://staging-otlp.nr-data.net`
4. **Check the endpoint:** Staging uses `staging-otlp.nr-data.net`; production uses `otlp.nr-data.net`
5. **Inspect locally:** Check `telemetry-data.json` for raw span data to confirm traces are being generated
6. **Check service name:** Verify traces have `service.name: strands-math-tutor` in New Relic UI

### 8.4 Agent returns errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OpenAIError: RateLimitError` | OpenAI API rate limit hit | Check usage at [platform.openai.com](https://platform.openai.com/account/rate-limits), wait, or upgrade plan |
| `OpenAIError: AuthenticationError` | Invalid or expired API key | Verify `OPENAI_API_KEY` in `.env` and at [platform.openai.com](https://platform.openai.com/account/api-keys) |
| `Timeout error` on `/prompt` | LLM response timeout | Increase Uvicorn timeout or optimize prompts |
| Agent returns incorrect math results | Model reasoning issue | Check agent system prompt; try simpler prompts or higher-quality models (e.g., `gpt-4o`) |

### 8.5 Tools not being called

- **Check agent logs:** Look for errors in the application output
- **Verify tool docstrings:** Each tool must have a docstring describing its purpose and arguments
- **Test with simple prompts:** Start with "What is 2 + 3?" to debug tool selection
- **Check LLM model:** Ensure the model (currently `gpt-4o`) supports function calling

### 8.6 Customizing the OTel exporter

**To switch from New Relic staging to production:**

Update the endpoint in `strands-otel-collector-config.yaml`:

```yaml
exporters:
  otlphttp/newrelic:
    endpoint: https://otlp.nr-data.net:4318    # Production endpoint
```

**To disable New Relic and only use local debugging:**

Replace the exporter in the pipeline:

```yaml
service:
  pipelines:
    traces:
      exporters: [logging, file]
```

**To view raw telemetry locally:**

Check the file exporter output:

```bash
cat telemetry-data.json | jq .  # Pretty-print JSON telemetry data
```

---

## 9. Latest Semantic Conventions (Recommended)

This implementation uses the **latest GenAI semantic conventions** with `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`. This is the recommended approach for the best data fidelity.

### 9.1 What Changed in Latest Conventions

**Legacy Approach (Event-per-Message)**:
- Emits individual `gen_ai.user.message`, `gen_ai.assistant.message`, `gen_ai.tool.message`, and `gen_ai.choice` span events
- Collector must iterate through events and extract messages
- Only last user message and final choice captured as attributes
- Tool input messages often missing from span attributes

**Latest Approach (Consolidated Messages)**:
- Emits a single `gen_ai.client.inference.operation.details` span event
- Contains pre-serialized `gen_ai.input.messages` and `gen_ai.output.messages` as JSON strings
- Complete conversation history is preserved
- All messages (user, assistant, tool) are captured
- Simpler collector transformation

### 9.2 How to Enable

Set this environment variable before starting the application:

```bash
export OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

Or add it to your `.env` file:

```env
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

This is already configured in the provided `.env` file.

### 9.3 Span Attributes in Latest Conventions

With the latest conventions enabled, each span includes:

| Attribute | Type | Example |
|-----------|------|---------|
| `gen_ai.input.messages` | String (JSON) | `[{"role":"user","parts":[{"type":"text","content":"What is 15 * 7?"}]}]` |
| `gen_ai.output.messages` | String (JSON) | `[{"role":"assistant","parts":[{"type":"text","content":"105"}],"finish_reason":"end_turn"}]` |
| `gen_ai.response.finish_reasons` | Array | `["end_turn"]` |
| `gen_ai.provider.name` | String | `strands-agents` |
| `gen_ai.request.model` | String | `gpt-4o` |
| `gen_ai.usage.input_tokens` | Integer | `455` |
| `gen_ai.usage.output_tokens` | Integer | `61` |

### 9.4 Message Format

**Input Messages (User Prompts)**:
```json
{
  "role": "user",
  "parts": [
    {
      "type": "text",
      "content": "What is 15 multiplied by 7?"
    }
  ]
}
```

**Output Messages (LLM Responses)**:
```json
{
  "role": "assistant",
  "parts": [
    {
      "type": "text",
      "content": "15 * 7 = 105. The result is 105."
    }
  ],
  "finish_reason": "end_turn"
}
```

### 9.5 Collector Configuration for Latest Conventions

The `transform/gen_ai_conversion` processor is configured to handle the latest conventions:

```yaml
transform/gen_ai_conversion:
  error_mode: ignore
  trace_statements:
    # Extract consolidated input/output from span events
    - context: spanevent
      conditions:
        - name == "gen_ai.client.inference.operation.details"
      statements:
        - 'set(span.attributes["gen_ai.input.messages"], attributes["gen_ai.input.messages"]) where name == "gen_ai.client.inference.operation.details"'
        - 'set(span.attributes["gen_ai.output.messages"], attributes["gen_ai.output.messages"]) where name == "gen_ai.client.inference.operation.details"'
        # Extract finish_reason from JSON output messages
        - 'set(span.attributes["gen_ai.response.finish_reasons"], attributes["gen_ai.output.messages"]) where name == "gen_ai.client.inference.operation.details" and IsMatch(attributes["gen_ai.output.messages"], ".*finish_reason.*")'
        - 'replace_pattern(span.attributes["gen_ai.response.finish_reasons"], "^[\\s\\S]*\"finish_reason\":\\s*\"", "")'
        - 'replace_pattern(span.attributes["gen_ai.response.finish_reasons"], "\"[\\s\\S]*$", "")'
    # Map provider name to system for New Relic compatibility
    - context: span
      statements:
        - 'set(attributes["gen_ai.system"], attributes["gen_ai.provider.name"]) where attributes["gen_ai.provider.name"] != nil and attributes["gen_ai.system"] == nil'
```

### 9.6 Example Trace Structure

With latest conventions, a simple math calculation produces:

```
Root Trace: 67f461f2853102a53caaf36539a8bb06

├── execute_event_loop_cycle (Cycle 1)
│   ├── chat (LLM Call #1)
│   │   ├── Span Attributes:
│   │   │   ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":"What is 15 * 7?"}]}]
│   │   │   ├── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"I'll use the multiply_numbers tool."}],"finish_reason":"tool_use"}]
│   │   │   ├── gen_ai.response.finish_reasons: ["tool_use"]
│   │   │   ├── gen_ai.request.model: gpt-4o
│   │   │   ├── gen_ai.usage.input_tokens: 455
│   │   │   ├── gen_ai.usage.output_tokens: 61
│   │   │   ├── gen_ai.usage.total_tokens: 516
│   │   │   └── gen_ai.server.time_to_first_token: 945
│   │   │
│   │   └── Span Event: gen_ai.client.inference.operation.details
│   │       ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":"What is 15 * 7?"}]}]
│   │       └── gen_ai.output.messages: [{"role":"assistant",...}]
│   │
│   └── execute_tool multiply_numbers
│       ├── gen_ai.tool.name: multiply_numbers
│       ├── gen_ai.tool.call.id: call_wpFGpymEc5OWlAASpuph3ysA
│       ├── gen_ai.tool.status: success
│       ├── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"15 * 7 = 105"}],"finish_reason":"end_turn"}]
│       └── Result: "15 * 7 = 105"
│
└── execute_event_loop_cycle (Cycle 2)
    └── chat (LLM Call #2)
        ├── gen_ai.input.messages: [{"role":"user","parts":[{"type":"text","content":"What is 15 * 7?"}]},{"role":"assistant","parts":[{"type":"toolUse","id":"call_...","name":"multiply_numbers","input":{"a":15,"b":7}}]},{"role":"user","parts":[{"type":"toolResult","toolUseId":"call_...","content":"15 * 7 = 105"}]}]
        ├── gen_ai.output.messages: [{"role":"assistant","parts":[{"type":"text","content":"The answer is 105."}],"finish_reason":"end_turn"}]
        ├── gen_ai.response.finish_reasons: ["end_turn"]
        ├── gen_ai.usage.input_tokens: 534
        ├── gen_ai.usage.output_tokens: 43
        └── gen_ai.usage.total_tokens: 577
```

**Key Observations:**
1. **Complete conversation history** — all user prompts, assistant responses, and tool interactions are captured
2. **Full message content** — including tool use details and results
3. **Clean JSON** — no double-escaping or concatenation hacks
4. **Tool tracking** — tool inputs and outputs are properly serialized in the message flow
5. **Token accounting** — per-call usage is tracked for accurate cost analysis

### 9.7 New Relic Integration

When traces are exported to New Relic, the service name is `strands-math-tutor` and includes:

- **AI Monitoring Tab**: Shows LLM calls with model, tokens, and latency
- **Trace Details**: Displays complete conversation history with all messages
- **Tool Execution**: Shows which tools were called and their results
- **Error Tracking**: Captures any tool execution failures

To view your traces:

1. Go to your New Relic account
2. Navigate to **APM > Services > strands-math-tutor**
3. Click on **AI Monitoring** (if available) or **Traces**
4. Select a trace to see the complete conversation flow
