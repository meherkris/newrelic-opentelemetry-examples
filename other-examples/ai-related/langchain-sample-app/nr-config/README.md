# Instrument your LangChain App with OpenTelemetry and New Relic

This guide walks you through everything needed to get your LangChain application sending telemetry to New Relic — from instrumenting your code to seeing data in AI Monitoring.

---

## How it works

```
Your LangChain App
  └── LangchainInstrumentor (OpenTelemetry auto-instrumentation)
        └── OTLP exporter → http://localhost:4318
                                    ↓
                      OTel Collector (Docker)
                        └── transform/gen_ai_conversion processor
                              maps Traceloop → gen_ai.* attributes
                                    ↓
                               New Relic
                          AI Monitoring Dashboard
```

---

## Step 1 — Instrument your LangChain app

LangChain telemetry is captured via [`opentelemetry-instrumentation-langchain`](https://pypi.org/project/opentelemetry-instrumentation-langchain/) auto-instrumentation. Add the following to your app **before** invoking any LangChain components:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

# 1. Set up TracerProvider first
prov = TracerProvider()
prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(prov)

# 2. Instrument LangChain — must happen before any agent/chain invocations
LangchainInstrumentor().instrument()

# 3. Now define your LangChain components
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
...
```

> **Note:** `OTLPSpanExporter()` with no arguments reads `OTEL_EXPORTER_OTLP_ENDPOINT` from the environment. Always set this to `http://localhost:4318` so spans route through the collector.

See the full example in [`langchain_app.py`](../langchain_app.py).

---

## Step 2 — Set `gen_ai.output.messages` manually

`LangchainInstrumentor` does not automatically set `gen_ai.output.messages`, which New Relic AI Monitoring requires to display the agent's response. Wrap each agent invocation in a custom root span and set this attribute:

```python
import json
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent_response") as span:
    result = await agent_executor.ainvoke({"input": request.prompt})
    span.set_attribute("gen_ai.output.messages", json.dumps([{
        "role": "assistant",
        "content": result["output"]
    }]))
```

Full example — [`langchain_app.py` lines 91–99](../langchain_app.py#L91-L99)

> `gen_ai.input.messages` is captured automatically by `LangchainInstrumentor` via Traceloop semantic conventions and does not need to be set manually.

---

## Step 3 — Configure the OTel Collector

The collector receives spans from your app and maps Traceloop attribute names to the `gen_ai.*` conventions New Relic requires. This mapping is done by the `transform/gen_ai_conversion` processor in [`langchain-test-collector-config.yaml`](./langchain-test-collector-config.yaml).

### What gets mapped

| Traceloop Attribute | New Relic (`gen_ai.*`) Attribute | Condition |
|---------------------|----------------------------------|-----------|
| `traceloop.workflow.name` | `gen_ai.agent.name` | Only on spans where `traceloop.span.kind == "workflow"` |
| `traceloop.entity.name` | `gen_ai.tool.name` | Only on spans where `traceloop.span.kind == "tool"` |

> **Using your own collector config?** Copy the `transform/gen_ai_conversion` processor block from [`langchain-test-collector-config.yaml` lines 28–36](./langchain-test-collector-config.yaml#L28-L36) into your config and add `transform/gen_ai_conversion` to your `traces` pipeline processors list.

### Enable New Relic AI Monitoring for OTel apps

To enable the **AI Monitoring** experience in New Relic for your OTel-instrumented LangChain app, add the `aiEnabledApp: "true"` tag to the `resource` processor in your collector config:

```yaml
processors:
  resource:
    attributes:
      - key: aiEnabledApp
        value: "true"
        action: insert
```

> Without this tag, your spans will still arrive in New Relic but the **AI Monitoring** section may not surface your app in its entity list. This is required for OTel-instrumented apps — apps using the New Relic agent get this automatically.

---

## Step 4 — Set environment variables

A `.env.example` file is provided at the project root with all required variables. Copy it and fill in your values:

```
cp ../.env.example ../.env
```

Then edit `../.env`:

```
OPENAI_API_KEY=<your_openai_api_key>
NEW_RELIC_LICENSE_KEY=<your_license_key>
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=langchain-test
# Replace langchain-test with the name you wish to call the application.
LLM_MODEL=gpt-4o   # optional, defaults to gpt-4o
```

The collector also needs `NEW_RELIC_LICENSE_KEY`. Create a `.env` file in this `nr-config/` directory:

```
NEW_RELIC_LICENSE_KEY=<your_license_key>
```

Replace `<your_license_key>` with your [Account License Key](https://one.newrelic.com/launcher/api-keys-ui.launcher).

> For EU accounts, update the endpoint in [`langchain-test-collector-config.yaml`](./langchain-test-collector-config.yaml):
> `endpoint: https://otlp.eu01.nr-data.net:4318`

---

## Step 5 — Start the OTel Collector

> The collector must be running before the app starts. Spans sent before the collector is ready will arrive in New Relic without `gen_ai.*` attributes.

```
docker compose -f docker-compose-langchain-test.yaml up -d
```

Confirm it is ready:

```
docker logs langchain-test-collector --since 10s
# Look for: "Everything is ready. Begin running and processing data."
```

---

## Step 6 — Run the application

From the project root:

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 venv/bin/uvicorn langchain_app:app --port 8080
```

> Always set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` explicitly. If your shell already has this variable set to an external endpoint, spans will bypass the collector and arrive in New Relic without the `gen_ai.*` mappings.

---

## Step 7 — Send a request and verify

```
curl -X POST http://localhost:8080/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 10 times 5?"}'
```

Check your [New Relic account](https://one.newrelic.com) under **AI Monitoring** or **All Entities > Services - OpenTelemetry** to confirm data is flowing. For EU users check your [account here](https://one.eu.newrelic.com).

---

## Troubleshooting

**No data in New Relic?**
- Confirm `NEW_RELIC_LICENSE_KEY` is set correctly in both `../.env` and `nr-config/.env`
- Check the collector is running: `docker ps | grep langchain-test-collector`
- Check collector logs for export errors: `docker logs langchain-test-collector --since 60s`
- For EU accounts, verify the endpoint in [`langchain-test-collector-config.yaml`](./langchain-test-collector-config.yaml) is set to `https://otlp.eu01.nr-data.net:4318`

**Spans arriving in New Relic but missing `gen_ai.*` attributes?**
- The app is likely sending spans directly to New Relic, bypassing the collector. Always start the app with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` explicitly set — your shell environment may be overriding it
- Confirm the collector was running *before* the app started

**`gen_ai.output.messages` missing?**
- This must be set manually in the app. Verify the wrapper span code is in place — see [`langchain_app.py` lines 91–99](../langchain_app.py#L91-L99)

**`gen_ai.agent.name` or `gen_ai.tool.name` missing?**
- These are mapped from Traceloop attributes by the collector. Confirm the `transform/gen_ai_conversion` processor is present in your collector config and listed in the `traces` pipeline — see [`langchain-test-collector-config.yaml` lines 28–36](./langchain-test-collector-config.yaml#L28-L36)

**LangChain spans not being captured at all?**
- `LangchainInstrumentor().instrument()` must be called before any LangChain agent or chain invocations. Check the initialization order in your app — see Step 1 above
- Confirm `opentelemetry-instrumentation-langchain` is installed: `pip show opentelemetry-instrumentation-langchain`

**App failing to connect to the collector?**
- Confirm the collector is listening on port `4318`: `docker logs langchain-test-collector | grep "4318"`
- Confirm no firewall or port conflict: `lsof -i :4318`

---

## Additional References

For a deep-dive into span structure, before/after attribute transformation examples, and known limitations, see [`DOCUMENTATION.md`](../DOCUMENTATION.md).

| Resource | Description |
|----------|-------------|
| [DOCUMENTATION.md](../DOCUMENTATION.md) | Full technical reference: span trees, attribute mapping details, known limitations |
| [New Relic AI Monitoring](https://docs.newrelic.com/docs/ai-monitoring/) | How New Relic ingests and displays AI telemetry |
| [New Relic Account License Key](https://one.newrelic.com/launcher/api-keys-ui.launcher) | Where to find your license key |
| [LangChain Documentation](https://python.langchain.com/docs/) | LangChain agents, tools, and LLM integrations |
| [Traceloop Semantic Conventions](https://github.com/traceloop/openllmetry) | Attribute names emitted by `LangchainInstrumentor` |
| [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Standard `gen_ai.*` attributes expected by New Relic |
| [OTel Collector Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor) | How the `transform/gen_ai_conversion` processor works |
| [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/) | OTel SDK setup and configuration reference |
