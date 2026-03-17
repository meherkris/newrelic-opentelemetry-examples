import os
import uvicorn
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()


otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

from strands import Agent, tool
from strands.telemetry import StrandsTelemetry
from strands.models.openai import OpenAIModel
from fastapi import FastAPI
from pydantic import BaseModel
# --- Define tools ---

@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result.

    Args:
        a: The first number.
        b: The second number.
    """
    return f"{a} + {b} = {a + b}"



@tool
def subtract_numbers(a: int, b: int) -> str:
    """Subtract b from a and return the result.

    Args:
        a: The number to subtract from.
        b: The number to subtract.
    """
    return f"{a} - {b} = {a - b}"


# --- Set up telemetry ---

strands_telemetry = StrandsTelemetry()
strands_telemetry.setup_otlp_exporter(endpoint=otel_endpoint)
strands_telemetry.setup_meter(
    enable_console_exporter=False,
    enable_otlp_exporter=True,
)

# --- Initialize FastAPI app ---

app = FastAPI(
    title="Strands Math Tutor Agent",
    description="Math tutor agent with Strands tools and OpenTelemetry instrumentation",
)

# --- Request/Response models ---

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

# --- System prompt ---

system_prompt = """You are a helpful math tutor who can perform calculations using the provided tools.
When asked a math question, use the appropriate tool (add, subtract) to compute the answer.
Always show your work and explain the steps clearly."""

# --- Create agent with tools ---

tools = [add_numbers, subtract_numbers]

openai_model = OpenAIModel(model_id=os.getenv("LLM_MODEL"))

agent = Agent(
    model=openai_model,
    system_prompt=system_prompt,
    tools=tools,
)

@app.post("/chat", response_model=PromptResponse)
async def prompt_agent(request: PromptRequest):
    """Send a prompt to the math tutor agent and get a response."""
    response = agent(request.prompt)
    return PromptResponse(response=str(response))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)