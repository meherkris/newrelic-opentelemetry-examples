import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# === SETUP: Langfuse SDK + OTLP Exporter to Collector ===
# Langfuse SDK creates an OTEL TracerProvider internally.
# AutoGen's auto-instrumented spans (agent calls, tool calls, LLM calls) are captured.
# We add an OTLP exporter so all spans are also sent to the OTEL collector.

from opentelemetry import trace
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from langfuse import get_client

# Initialize Langfuse (sets up TracerProvider, no scopes blocked)
langfuse = get_client()

# Add OTLP exporter to send all spans to the collector
tracer_provider = trace.get_tracer_provider()
otlp_exporter = OTLPSpanExporter(
    endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
OpenAIInstrumentor().instrument()

# Import dependencies
from fastapi import FastAPI
from pydantic import BaseModel
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient


app = FastAPI()

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

# Get model name from environment
model_name = os.getenv("LLM_MODEL", "gpt-4o")

def add_tool(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


def subtract_tool(a: float, b: float) -> float:
    """Subtract second number from first number."""
    return a - b


@app.post("/chat", response_model=PromptResponse)
async def chat(request: PromptRequest):
    # Use Langfuse context manager for better integration
    with langfuse.start_as_current_observation(as_type="span", name="calculator-agent"):
        model_client = OpenAIChatCompletionClient(model=model_name)

        # Create a math calculation agent with add and subtract tools
        math_agent = AssistantAgent(
            "MathAgent",
            description="An agent that performs basic math calculations like addition and subtraction.",
            model_client=model_client,
            tools=[add_tool, subtract_tool],
            system_message="""
            You are a math calculation agent.
            You have two tools available:
            - add_tool: Adds two numbers together
            - subtract_tool: Subtracts the second number from the first

            Use these tools to solve math problems.
            After you calculate the result, respond with your answer.
            """,
        )

        # Create a validator agent to check the math agent's work
        validator_agent = AssistantAgent(
            "ValidatorAgent",
            description="An agent that validates and explains mathematical calculations.",
            model_client=model_client,
            system_message="""
            You are a validator agent.
            Your job is to:
            1. Review the calculation performed by the MathAgent
            2. Verify if the result is correct
            3. Provide a brief explanation of the calculation
            4. If everything is correct, say "APPROVED" to end the conversation

            Be concise and clear in your validation.
            """,
        )

        # Create a RoundRobinGroupChat to orchestrate between agents
        team = RoundRobinGroupChat(
            [math_agent, validator_agent],
            termination_condition=TextMentionTermination("APPROVED") | MaxMessageTermination(10),
        )

        # Run the task through the team
        result = await team.run(task=request.prompt)

        # Combine all messages into response
        response_text = "\n\n".join([
            f"[{msg.source}]: {msg.content}"
            for msg in result.messages
        ])

        await model_client.close()

        return PromptResponse(response=response_text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
