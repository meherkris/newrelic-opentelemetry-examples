# Instrument your Strands Agent App with OpenTelemetry and New Relic

This guide walks you through everything needed to get your Strands Agents application sending telemetry to New Relic — from instrumenting your code to seeing data in AI Monitoring.

---

## How it works

```
Your Strands Agents App
  └── StrandsTelemetry (built-in OTel integration)
        └── OTLP exporter → http://localhost:4318
                                    ↓
                      OTel Collector (Docker)
                        └── transform/gen_ai_conversion processor
                              extracts gen_ai.* from span events
                              maps gen_ai.provider.name → gen_ai.system
                                    ↓
                               New Relic
                          AI Monitoring Dashboard
```

---

## Step 1 — Instrument your Strands Agents app

Strands Agents has built-in OpenTelemetry support via `StrandsTelemetry`. Add the following to your app **before** creating an agent:

```python
from strands import Agent, tool
from strands.telemetry import StrandsTelemetry
from strands.models.openai import OpenAIModel

# 1. Set up telemetry — must happen before creating the agent
strands_telemetry = StrandsTelemetry()
strands_telemetry.setup_otlp_exporter(endpoint="http://localhost:4318/v1/traces")
strands_telemetry.setup_meter(
    enable_console_exporter=False,
    enable_otlp_exporter=True,
)

# 2. Define your tools
@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result."""
    return f"{a} + {b} = {a + b}"

# 3. Create the agent
openai_model = OpenAIModel(model_id="gpt-4o")
agent = Agent(
    model=openai_model,
    system_prompt="You are a helpful math tutor...",
    tools=[add_numbers],
)
```

> **Order matters:** `StrandsTelemetry` must be configured before any agent is created, otherwise spans will not be captured.

See the full example in [`strands_app.py`](../strands_app.py).

---

## Step 2 — How Strands emits telemetry (no manual spans needed)

Unlike some other frameworks, Strands Agents natively emits `gen_ai.*` attributes using the **latest OTel GenAI semantic conventions** (`gen_ai_latest_experimental`). You do **not** need to manually set input/output messages in your app code.

Strands emits these as **span events** on LLM spans with the event name `gen_ai.client.inference.operation.details`:

```
Span: strands agent (root)
  └── gen_ai.agent.name: <agent name>
      └── Span: <LLM call>
            └── SpanEvent: gen_ai.client.inference.operation.details
                  ├── gen_ai.input.messages:  [{"role":"user","content":"..."}]
                  ├── gen_ai.output.messages: [{"role":"assistant","content":"...","finish_reason":"stop"}]
                  └── (finish_reason embedded in output messages JSON)
```

The OTel Collector extracts these from span events and promotes them to span attributes — see Step 3.

### Required environment variable

Set this in your `.env` to activate the latest GenAI semantic conventions:

```
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

Without this, Strands may fall back to older attribute names that New Relic does not recognize.

---

## Step 3 — Configure the OTel Collector

The collector receives spans from your app and:
1. Promotes `gen_ai.input.messages` and `gen_ai.output.messages` from span events to span attributes
2. Extracts `gen_ai.response.finish_reasons` from the output messages JSON
3. Maps `gen_ai.provider.name` (latest convention) → `gen_ai.system` (required by New Relic)

This is handled by the `transform/gen_ai_conversion` processor in [`strands-otel-collector-config.yaml`](./strands-otel-collector-config.yaml).

### What gets mapped

| Source | New Relic (`gen_ai.*`) Attribute | Description |
|--------|----------------------------------|-------------|
| SpanEvent `gen_ai.input.messages` | `gen_ai.input.messages` (span attr) | Promoted from span event to span attribute |
| SpanEvent `gen_ai.output.messages` | `gen_ai.output.messages` (span attr) | Promoted from span event to span attribute |
| SpanEvent `gen_ai.output.messages` (regex) | `gen_ai.response.finish_reasons` | `finish_reason` value extracted from output JSON |
| `gen_ai.provider.name` | `gen_ai.system` | Provider name mapped to legacy attribute New Relic requires |

> **Using your own collector config?** Copy the `transform/gen_ai_conversion` processor block from [`strands-otel-collector-config.yaml` lines 27–45](./strands-otel-collector-config.yaml#L27-L45) into your config and add `transform/gen_ai_conversion` to your `traces` pipeline processors list.

### Enable New Relic AI Monitoring for OTel apps

To enable the **AI Monitoring** experience in New Relic for your OTel-instrumented Strands app, add the `aiEnabledApp: "true"` tag to the `resource` processor in your collector config:

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

A `.env.example` file is provided at the project root. Copy it and fill in your values:

```
cp ../.env.example ../.env
```

Then edit `../.env`:

```
OPENAI_API_KEY=<your_openai_api_key>
NEW_RELIC_LICENSE_KEY=<your_license_key>
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=strands-math-tutor
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
```

The collector also needs `NEW_RELIC_LICENSE_KEY`. Create a `.env` file in this `nr-config/` directory:

```
NEW_RELIC_LICENSE_KEY=<your_license_key>
```

Replace `<your_license_key>` with your [Account License Key](https://one.newrelic.com/launcher/api-keys-ui.launcher).

> For EU accounts, update the endpoint in [`strands-otel-collector-config.yaml`](./strands-otel-collector-config.yaml):
> `endpoint: https://otlp.eu01.nr-data.net:4318`

---

## Step 5 — Start the OTel Collector

> The collector must be running before the app starts. Spans sent before the collector is ready will arrive in New Relic without the `gen_ai.*` attribute promotions.

```
docker compose -f docker-compose-strands.yaml up -d
```

Confirm it is ready:

```
docker logs strands-otel-collector --since 10s
# Look for: "Everything is ready. Begin running and processing data."
```

---

## Step 6 — Run the application

From the project root:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn strands_app:app --reload
```

> Always ensure `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` points to the local collector. If your shell already has this variable set to an external endpoint, spans will bypass the collector and arrive in New Relic without the `gen_ai.*` attribute promotions.

---

## Step 7 — Send a request and verify

```
curl -X POST http://localhost:8000/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 25 times 4?"}'
```

Check your [New Relic account](https://one.newrelic.com) under **AI Monitoring** or **All Entities > Services - OpenTelemetry** to confirm data is flowing. For EU users check your [account here](https://one.eu.newrelic.com).

---

## Troubleshooting

**No data in New Relic?**
- Confirm `NEW_RELIC_LICENSE_KEY` is set correctly in both `../.env` and `nr-config/.env`
- Check the collector is running: `docker ps | grep strands-otel-collector`
- Check collector logs for export errors: `docker logs strands-otel-collector --since 60s`
- For EU accounts, verify the endpoint in [`strands-otel-collector-config.yaml`](./strands-otel-collector-config.yaml) is set to `https://otlp.eu01.nr-data.net:4318`

**Spans arriving in New Relic but missing `gen_ai.*` attributes?**
- The app is likely sending spans directly to New Relic, bypassing the collector. Always start the app with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` explicitly set
- Confirm the collector was running *before* the app started

**`gen_ai.input.messages` / `gen_ai.output.messages` missing on spans?**
- These are extracted from span events by the collector. Confirm `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` is set in your `.env` — without it Strands will not emit the `gen_ai.client.inference.operation.details` span event
- Verify the `transform/gen_ai_conversion` processor is active in the collector config and listed in the `traces` pipeline

**`gen_ai.response.finish_reasons` missing?**
- This is extracted from the `gen_ai.output.messages` JSON via regex in the collector. Confirm the `transform/gen_ai_conversion` processor block is present and the `gen_ai.output.messages` span event attribute contains a `finish_reason` field

**`gen_ai.system` missing?**
- The collector maps `gen_ai.provider.name` → `gen_ai.system`. Confirm the span-context statement is present in your `transform/gen_ai_conversion` processor config

**App not appearing in AI Monitoring entity list?**
- Add `aiEnabledApp: "true"` to the `resource` processor — see Step 3 above

**Collector fails to start?**
- Check config syntax: `docker logs strands-otel-collector`
- After any config change, restart: `docker restart strands-otel-collector`

---

## Additional References

For a deep-dive into span structure, attribute details, and known limitations, see [`DOCUMENTATION.md`](../DOCUMENTATION.md).

| Resource | Description |
|----------|-------------|
| [DOCUMENTATION.md](../DOCUMENTATION.md) | Full technical reference: span trees, attribute mapping details, known limitations |
| [New Relic AI Monitoring](https://docs.newrelic.com/docs/ai-monitoring/) | How New Relic ingests and displays AI telemetry |
| [New Relic Account License Key](https://one.newrelic.com/launcher/api-keys-ui.launcher) | Where to find your license key |
| [Strands Agents SDK](https://github.com/strands-agents/sdk-python) | Strands Agents SDK, tools, and model integrations |
| [OTel GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Standard `gen_ai.*` attributes expected by New Relic |
| [OTel Collector Transform Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor) | How the `transform/gen_ai_conversion` processor works |
| [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/) | OTel SDK setup and configuration reference |
