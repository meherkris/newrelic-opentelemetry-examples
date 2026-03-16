# Strands Math Tutor Agent

A FastAPI-based math tutor agent built with [Strands Agents](https://github.com/strands-agents) and OpenAI GPT-4o, featuring full observability through OpenTelemetry and New Relic.

## Overview

This application demonstrates how to build an AI agent with tool-use capabilities while maintaining production-grade observability. The agent accepts math questions via a REST API, uses dedicated math tools (add, subtract, multiply, divide) to compute answers, and returns explanations.

## Tech Stack

- **Agent Framework:** Strands Agents (with OpenAI provider)
- **LLM:** OpenAI GPT-4o
- **Web Framework:** FastAPI + Uvicorn
- **Observability:** OpenTelemetry SDK → OTel Collector → New Relic
- **Language:** Python 3.12

## Project Structure

```
├── strands_app.py                       # Main application (API + agent + tools)
├── requirements.txt                     # Python dependencies
├── .env                                 # Environment variables (API keys, config)
├── docker-compose-strands.yaml          # Docker Compose for OTel Collector
├── strands-otel-collector-config.yaml   # OTel Collector pipeline configuration
└── .venv/                               # Python virtual environment
```

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- An OpenAI API key
- A New Relic license key (for telemetry export)

## Setup

1. **Clone the repository and create a virtual environment:**

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**

   Create a `.env` file with the following:

   ```env
   OPENAI_API_KEY=<your-openai-api-key>
   NEW_RELIC_LICENSE_KEY=<your-new-relic-license-key>
   OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   OTEL_SERVICE_NAME=strands-math-tutor
   OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
   ```

4. **Enable New Relic AI Monitoring:**

   To surface your app in New Relic's **AI Monitoring** section, add `aiEnabledApp: "true"` to the `resource` processor in your OTel Collector config ([`nr-config/strands-otel-collector-config.yaml`](nr-config/strands-otel-collector-config.yaml)):

   ```yaml
   processors:
     resource:
       attributes:
         - key: aiEnabledApp
           value: "true"
           action: insert
   ```

   > This is required for OTel-instrumented apps. Without it, spans arrive in New Relic but the app will not appear in the AI Monitoring entity list. Apps using the New Relic agent get this automatically.

5. **Start the OpenTelemetry Collector:**

   ```bash
   docker-compose -f docker-compose-strands.yaml up -d
   ```

6. **Run the application:**

   ```bash
   uvicorn strands_app:app --reload
   ```

   The API will be available at `http://localhost:8000`.

## API Usage

### Endpoints

| Method | Path      | Description                |
|--------|-----------|----------------------------|
| GET    | `/`       | Health check               |
| POST   | `/prompt` | Send a math question       |

### Example Request

```bash
curl -X POST "http://localhost:8000/prompt" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 25 times 4?"}'
```

### Interactive Docs

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Available Tools

The agent has access to four math tools:

| Tool               | Description                          |
|--------------------|--------------------------------------|
| `add_numbers`      | Adds two integers                    |
| `subtract_numbers` | Subtracts two integers               |
| `multiply_numbers` | Multiplies two integers              |
| `divide_numbers`   | Divides two integers (zero-safe)     |

## Observability

### Architecture

```
FastAPI App → Strands Telemetry (OTel SDK) → OTel Collector → New Relic
```

### What's Instrumented

- Agent execution traces
- Individual tool invocations
- LLM API calls (including input/output content)
- Token usage metrics

### OTel Collector

The collector runs as a Docker container and is configured with:

- **Receivers:** OTLP over gRPC (`:4317`) and HTTP (`:4318`)
- **Processors:** Memory limiter, batching, resource attributes, Gen AI semantic convention transforms
- **Exporters:** New Relic (OTLP/HTTP), console logging, optional file output

### Ports

| Port  | Protocol   | Service              |
|-------|------------|----------------------|
| 8000  | HTTP       | FastAPI application  |
| 4317  | gRPC       | OTel Collector OTLP  |
| 4318  | HTTP       | OTel Collector OTLP  |
| 55679 | HTTP       | ZPages (debug UI)    |
