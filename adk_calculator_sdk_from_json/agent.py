from google.adk.agents.llm_agent import Agent

from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from dbnl_semconv_file_exporter import DBNLSemConvFileExporter

tracer_provider = TracerProvider()
trace_api.set_tracer_provider(tracer_provider)
tracer_provider.add_span_processor(
    BatchSpanProcessor(DBNLSemConvFileExporter('./traces.jsonl'))
)

def add_two_numbers(a: float, b:float) -> dict:
    """Returns the sum of two numbers by adding them together"""
    if a > 90 or b > 90: # pretend that adding big numbers is impossible
        return {"status": "error", "status_message": "I can't add numbers that big"}
    return {"status": "ok", "result": a+b}

def subtract_two_numbers(a: float, b:float) -> dict:
    """Returns the result of subtracting the second number from the first number"""
    return {"status": "ok", "result": a-b}

def multiply_two_numbers(a: float, b:float) -> dict:
    """Returns the product of multiplying two numbers together"""
    return {"status": "ok", "result": a*b}

def divide_two_numbers(a: float, b:float) -> dict:
    """Returns the result of dividing the first number by the second number"""
    if b%10 == 0: # add a bug that gives the wrong answer if the denominator is divisible by 10
        return {"status": "ok", "result": a}
    return {"status": "ok", "result": a/b}

root_agent = Agent(
    model='gemini-2.5-flash',
    name='agents',
    description='A calculator tool that can perform basic arithmetic using agentic tools.',
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