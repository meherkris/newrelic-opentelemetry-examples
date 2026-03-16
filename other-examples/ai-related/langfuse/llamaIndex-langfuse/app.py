import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

# Configure OpenTelemetry to send traces to OTEL collector
# Setup OpenTelemetry TracerProvider to send traces to OTEL collector
from opentelemetry import trace

otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otel_endpoint:
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
from langfuse import get_client
from llama_index.core.agent.workflow import ReActAgent
from llama_index.llms.openai import OpenAI
from llama_index.core.tools import FunctionTool

from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

# Initialize Langfuse client
langfuse = get_client()

# Initialize LlamaIndex instrumentation
LlamaIndexInstrumentor().instrument()

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

# Get model name from environment (without prefix, LlamaIndex handles it directly)
model_name = os.getenv("LLM_MODEL", "gpt-4o")

# Define simple calculator tools
def add(a: float, b: float) -> float:
    """Useful for adding two numbers."""
    return a + b

def subtract(a: float, b: float) -> float:
    """Useful for subtracting two numbers."""
    return a - b

tools = [
    FunctionTool.from_defaults(add),
    FunctionTool.from_defaults(subtract),
]

# Create an agent workflow with our calculator tool
agent = ReActAgent(
    tools=tools,
    llm=OpenAI(model=model_name, 
    additional_kwargs={
        "stream_options": {"include_usage": True}
    }
    ),
    system_prompt="You are a helpful assistant that can add or subtract two numbers.",
)

@app.post("/chat", response_model=PromptResponse)
async def chat(request: PromptRequest):
    # Use Langfuse context manager to create a parent span for all operations
    with langfuse.start_as_current_observation(as_type="span", name="calculator-agent"):

        response = await agent.run(request.prompt)

        # Set gen_ai input/output messages on the current OTel span
        span = trace.get_current_span()
        span.set_attribute("gen_ai.input.messages", json.dumps([{"role": "user", "content": request.prompt}]))
        span.set_attribute("gen_ai.output.messages", json.dumps([{"role": "assistant", "content": str(response)}]))

        # Flush to ensure data is sent to OTEL collector
        langfuse.flush()

        return PromptResponse(response=str(response))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




