import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv, find_dotenv

# LangChain Imports
from langchain_openai import ChatOpenAI
from langchain.agents import create_openai_tools_agent, AgentExecutor
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Telemetry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.langchain import LangchainInstrumentor

# Load environment variables
load_dotenv(find_dotenv(), override=True)

# --- 1. Set up Telemetry ---
# Note: LangChain instrumentation hooks into the underlying calls automatically
prov = TracerProvider()
prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(prov)

# Initialize the LangChain instrumentation
LangchainInstrumentor().instrument()

# --- 2. Define Tools ---
@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together and return the result."""
    return f"{a} + {b} = {a + b}"

@tool
def subtract_numbers(a: int, b: int) -> str:
    """Subtract b from a and return the result."""
    return f"{a} - {b} = {a - b}"

@tool
def multiply_numbers(a: int, b: int) -> str:
    """Multiply two numbers together and return the result."""
    return f"{a} * {b} = {a * b}"

@tool
def divide_numbers(a: int, b: int) -> str:
    """Divide a by b and return the result. Returns error if b is zero."""
    if b == 0:
        return "Error: Cannot divide by zero"
    return f"{a} / {b} = {a / b}"

tools = [add_numbers, subtract_numbers, multiply_numbers, divide_numbers]

# --- 3. Initialize Agent ---
llm = ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o"), temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful math tutor who can perform calculations using the provided tools. Always show your work and explain the steps clearly."),
    ("user", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_openai_tools_agent(
    llm=llm,
    tools=tools,
    prompt=prompt,
)

agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, name="MathTutorAgent")

# --- 4. FastAPI Setup ---
app = FastAPI(
    title="LangChain Math Tutor Agent",
    description="Math tutor agent with LangChain tools and OpenTelemetry instrumentation",
)

class PromptRequest(BaseModel):
    prompt: str

class PromptResponse(BaseModel):
    response: str

@app.post("/prompt", response_model=PromptResponse)
async def prompt_agent(request: PromptRequest):
    # LangChain instrumentation automatically traces all operations
    # LangchainInstrumentor captures all spans with semantic conventions
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("agent_response") as span:
        result = await agent_executor.ainvoke({"input": request.prompt})
        # Set the response attribute in New Relic format (array of message objects)
        import json
        output_messages = json.dumps([{
            "role": "assistant",
            "content": result["output"]
        }])
        span.set_attribute("gen_ai.output.messages", output_messages)

    return PromptResponse(response=result["output"])
