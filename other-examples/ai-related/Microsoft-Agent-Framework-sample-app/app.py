import os
import socket
from importlib.metadata import version

from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# ── OpenTelemetry Setup ──────────────────────────────────────────────────────

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.semconv.resource import ResourceAttributes

SDK_LANGUAGE = f"python"
# Setup OpenTelemetry with OTLP exporter
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    resource = Resource(attributes={
        SERVICE_NAME: os.getenv("OTEL_SERVICE_NAME", "microsoft-agent-framework-app"),
        ResourceAttributes.TELEMETRY_SDK_NAME: trace.__name__.split('.')[0],  # Dynamically gets "opentelemetry"
        ResourceAttributes.TELEMETRY_SDK_LANGUAGE: SDK_LANGUAGE,
        ResourceAttributes.TELEMETRY_SDK_VERSION: version("opentelemetry-sdk"),
        ResourceAttributes.HOST_NAME: socket.gethostname(),
    })
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=f"{otel_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    trace.set_tracer_provider(provider)


# ── Imports ───────────────────────────────────────────────────────────────────

from fastapi import FastAPI
from pydantic import BaseModel


from agent_framework.observability import configure_otel_providers

configure_otel_providers(enable_sensitive_data=True)

from agent_framework.openai import OpenAIChatCompletionClient
from typing import Annotated
from pydantic import Field
from random import randint

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."

class ChatRequest(BaseModel):
    prompt: str


app = FastAPI()


async def process_agent_query(prompt: str):
    async with OpenAIChatCompletionClient(model=os.getenv("OPENAI_RESPONSES_MODEL_ID")).as_agent(
        name="WeatherAssistant",
        instructions="You are a helpful assistant.",
        tools=get_weather,
    ) as agent:
        result = await agent.run(prompt)
        return result


@app.post("/chat")
async def chat(request: ChatRequest):
    result = await process_agent_query(request.prompt)
    return {"response": result.text}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
