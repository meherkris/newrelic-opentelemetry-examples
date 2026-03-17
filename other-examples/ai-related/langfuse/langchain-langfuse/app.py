import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
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
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langchain.agents import create_agent

langfuse = get_client()

app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

# Get model name from environment (with openai: prefix as per Langfuse docs)
model_name = os.getenv("LLM_MODEL", "gpt-4o")

def add_numbers(a: int, b: int) -> int:
    """Add two numbers together and return the result."""
    return a + b

def subtract_numbers(a: int, b: int) -> int:
    """Subtract two numbers and return the result."""
    return a - b    

# Create agent with the tool
agent = create_agent(
    model=model_name,
    tools=[add_numbers,subtract_numbers],
    system_prompt="You are a helpful math tutor who can do calculations using the provided tools.",
)

@app.post("/chat", response_model=PromptResponse)
async def chat(request: PromptRequest):
    # Initialize handler for this request
    langfuse_handler = CallbackHandler()

    # Invoke agent with Langfuse callback handler
    response = agent.invoke(
        {"messages": [{"role": "user", "content": request.prompt}]},
        config={
            "callbacks": [langfuse_handler],
            "run_name": "math_tutor_agent"
        }
    )

    # Extract the actual response content from the agent's output
    # Response is a dict with 'messages' key containing AIMessage objects
    if isinstance(response, dict) and "messages" in response:
        # Get the last message
        last_message = response["messages"][-1]
        # AIMessage has a 'content' attribute
        response_content = last_message.content if hasattr(last_message, 'content') else str(last_message)
    else:
        # Fallback to string representation
        response_content = str(response)

    return PromptResponse(response=response_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)




