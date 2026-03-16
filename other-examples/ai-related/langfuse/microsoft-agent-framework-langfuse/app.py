import os

from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Setup OpenTelemetry TracerProvider to send traces to OTEL collector (must be before Langfuse import)
otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    import socket
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create(attributes={"host": socket.gethostname()})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otel_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)



from fastapi import FastAPI
from pydantic import BaseModel


from agent_framework.observability import configure_otel_providers
configure_otel_providers(enable_sensitive_data=True)

from agent_framework.openai import OpenAIResponsesClient
from typing import Annotated
from pydantic import Field


def add(
    a: Annotated[float, Field(description="The first number.")],
    b: Annotated[float, Field(description="The second number.")],
) -> float:
    """Add two numbers together."""
    return a + b


def subtract(
    a: Annotated[float, Field(description="The first number.")],
    b: Annotated[float, Field(description="The number to subtract.")],
) -> float:
    """Subtract the second number from the first."""
    return a - b
 
class ChatRequest(BaseModel):
    prompt: str


app = FastAPI()


async def process_agent_query(prompt: str):
    async with OpenAIResponsesClient().as_agent(
        name="MathAssistant",
        instructions="You are a helpful math assistant that can add and subtract numbers.",
        tools=[add, subtract],
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