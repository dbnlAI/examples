from google.adk.agents.llm_agent import Agent

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from openinference.instrumentation.google_adk import GoogleADKInstrumentor

provider = TracerProvider()
trace.set_tracer_provider(provider)

exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318/v1/traces",  # matches your otelcol http receiver
)

processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)

GoogleADKInstrumentor().instrument(tracer_provider=provider)


def add_two_numbers(a: float, b: float) -> dict:
    """Returns the sum of two numbers by adding them together"""
    return {"status": "ok", "result": a + b}


def subtract_two_numbers(a: float, b: float) -> dict:
    """Returns the result of subtracting the second number from the first number"""
    return {"status": "ok", "result": a - b}


def multiply_two_numbers(a: float, b: float) -> dict:
    """Returns the product of multiplying two numbers together"""
    return {"status": "ok", "result": a * b}


def divide_two_numbers(a: float, b: float) -> dict:
    """Returns the result of dividing the first number by the second number"""
    return {"status": "ok", "result": a / b}


root_agent = Agent(
    model="gemini-2.5-flash",
    name="agents",
    description="A calculator tool that can perform basic arithmetic using agentic tools.",
    instruction='Answer user math questions using the tools available to you, even if there are errors or inaccurate responses from the tools. Always respond with just the answer, do not show your work or repeat the question, do not add extra text. If you cannot get the answer from using the provided tools then you should not provide the response "I cannot answer that.", only use the information from the tools to perform addition, subtraction, multiplication, and division. Do not evaluate the input without using the tools. Do not try to correct mistakes made by the tools.',
    tools=[
        add_two_numbers,
        subtract_two_numbers,
        multiply_two_numbers,
        divide_two_numbers,
    ],
)


def get_agent():
    return root_agent
