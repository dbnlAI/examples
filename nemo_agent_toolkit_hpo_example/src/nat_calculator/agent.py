# SPDX-FileCopyrightText: Copyright (c) 2025
# SPDX-License-Identifier: Apache-2.0

"""Google Gemini Calculator Agent for NeMo Agent Toolkit.

This version uses the google.genai SDK with OpenInference instrumentation
to capture tool calls in OTEL traces.
"""

import json
import logging
import math
import os
import time
from typing import Any

from pydantic import Field

from nat.builder.builder import Builder  # type: ignore[import-untyped]
from nat.builder.function_info import FunctionInfo  # type: ignore[import-untyped]
from nat.cli.register_workflow import register_function  # type: ignore[import-untyped]
from nat.data_models.function import FunctionBaseConfig  # type: ignore[import-untyped]
from nat.data_models.optimizable import OptimizableField, OptimizableMixin, SearchSpace  # type: ignore[import-untyped]

# OpenTelemetry and OpenInference instrumentation
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor  # type: ignore[import-untyped]

# Set up our own TracerProvider for OpenInference spans
# This exports to the same OTEL collector as NAT
_provider = TracerProvider()
_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
_processor = BatchSpanProcessor(_exporter)
_provider.add_span_processor(_processor)

# Set as global provider so OpenInference uses it
trace.set_tracer_provider(_provider)

# Instrument the google.genai SDK
GoogleGenAIInstrumentor().instrument()

# Get a tracer for our own spans
_tracer = trace.get_tracer("nat_calculator")

logger = logging.getLogger(__name__)


class CalculatorAgentConfig(
    FunctionBaseConfig, OptimizableMixin, name="adk_calculator"
):  # type: ignore[call-arg]
    """Configuration for the calculator agent with optimizable parameters."""

    name: str = Field(default="calculator_agent")
    description: str = Field(
        default="A calculator tool that can perform basic arithmetic using agentic tools."
    )
    model_name: str = OptimizableField(
        default="gemini-2.0-flash",
        space=SearchSpace(
            values=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
        ),
        description="Gemini model to use",
    )
    temperature: float = OptimizableField(
        default=0.0,
        space=SearchSpace(low=0.0, high=0.8, step=0.1),
        description="Temperature for response generation",
    )
    hyper_error_term: float = OptimizableField(
        default=1.0,
        space=SearchSpace(low=-1.0, high=1.0),
        description="Error term added to calculator results for HPO testing",
    )
    prompt: str = OptimizableField(
        default=(
            "Answer user math questions using the tools available to you, even if there "
            "are errors or inaccurate responses from the tools. Always respond with just "
            "the answer, do not show your work or repeat the question, do not add extra "
            "text. If you cannot get the answer from using the provided tools then you "
            'should not provide the response "I cannot answer that.", only use the '
            "information from the tools to perform addition, subtraction, multiplication, "
            "and division. Do not evaluate the input without using the tools. Do not try "
            "to correct mistakes made by the tools."
        ),
        space=SearchSpace(is_prompt=True),
        description="System prompt for the calculator agent",
    )
    user_id: str = Field(default="nat")


# Global variable to store hyper_error_term for tool execution
_current_hyper_error_term = 1.0


def add_two_numbers(a: float, b: float) -> dict[str, Any]:
    """Returns the sum of two numbers by adding them together.

    Args:
        a: First number
        b: Second number
    """
    result = a + b
    error_term = _current_hyper_error_term / (1.0 + math.exp(100 - a - b))
    return {"status": "ok", "result": result + error_term}


def subtract_two_numbers(a: float, b: float) -> dict[str, Any]:
    """Returns the result of subtracting the second number from the first.

    Args:
        a: First number
        b: Second number to subtract
    """
    result = a - b
    error_term = _current_hyper_error_term / (1.0 + math.exp(100 - a - b))
    return {"status": "ok", "result": result + error_term}


def multiply_two_numbers(a: float, b: float) -> dict[str, Any]:
    """Returns the product of multiplying two numbers together.

    Args:
        a: First number
        b: Second number
    """
    result = a * b
    error_term = _current_hyper_error_term / (1.0 + math.exp(100 - a - b))
    return {"status": "ok", "result": result + error_term}


def divide_two_numbers(a: float, b: float) -> dict[str, Any]:
    """Returns the result of dividing the first number by the second.

    Args:
        a: First number (dividend)
        b: Second number (divisor)
    """
    if b == 0:
        return {"status": "error", "result": "Cannot divide by zero"}
    result = a / b
    error_term = _current_hyper_error_term / (1.0 + math.exp(100 - a - b))
    return {"status": "ok", "result": result + error_term}


@register_function(config_type=CalculatorAgentConfig)
async def adk_calculator_agent(config: CalculatorAgentConfig, builder: Builder):
    """Calculator agent using google.genai SDK with OpenInference instrumentation."""
    from google import genai  # type: ignore[import-untyped]
    from google.genai import types  # type: ignore[import-untyped]

    global _current_hyper_error_term
    _current_hyper_error_term = config.hyper_error_term

    # Create client
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    # Tool list for the model
    tools = [
        add_two_numbers,
        subtract_two_numbers,
        multiply_two_numbers,
        divide_two_numbers,
    ]

    async def _response_fn(input_message: str) -> str:
        """Process user input and return agent response using Gemini with tool calls."""
        from opentelemetry.trace import StatusCode

        # Create a parent span that will contain all Gemini API calls
        # This ensures all spans share the same trace_id
        with _tracer.start_as_current_span("calculator_agent") as span:
            # Set input on the span
            span.set_attribute("input.value", input_message)
            span.set_attribute("input.mime_type", "text/plain")

            # Rate limiting
            time.sleep(0.5)

            # Configure generation with tools and automatic function calling disabled
            # so we can handle them ourselves with the error term
            gen_config = types.GenerateContentConfig(
                temperature=config.temperature,
                system_instruction=config.prompt,
                tools=tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            )

            # Build conversation history
            contents = [
                types.Content(
                    role="user", parts=[types.Part.from_text(text=input_message)]
                )
            ]

            max_iterations = 10
            response = None
            for _ in range(max_iterations):
                response = client.models.generate_content(
                    model=config.model_name,
                    contents=contents,
                    config=gen_config,
                )

                # Check for function calls
                if not response.candidates:
                    break

                candidate = response.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    break

                # Collect function calls and text
                function_calls = []
                text_parts = []

                for part in candidate.content.parts:
                    if part.function_call:
                        function_calls.append(part)
                    elif part.text:
                        text_parts.append(part.text)

                # If no function calls, return text response
                if not function_calls:
                    result = "".join(text_parts) if text_parts else ""
                    span.set_attribute("output.value", result)
                    span.set_attribute("output.mime_type", "text/plain")
                    span.set_status(StatusCode.OK)
                    return result

                # Add assistant's response to history
                contents.append(candidate.content)

                # Execute function calls and build response
                function_response_parts = []
                for fc_part in function_calls:
                    fc = fc_part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    # Find and execute the tool with a TOOL span
                    tool_fn = {
                        "add_two_numbers": add_two_numbers,
                        "subtract_two_numbers": subtract_two_numbers,
                        "multiply_two_numbers": multiply_two_numbers,
                        "divide_two_numbers": divide_two_numbers,
                    }.get(tool_name)

                    # Create a TOOL span for the function execution
                    with _tracer.start_as_current_span(tool_name) as tool_span:
                        tool_span.set_attribute("openinference.span.kind", "TOOL")
                        tool_span.set_attribute("tool.name", tool_name)
                        tool_span.set_attribute(
                            "tool.parameters", json.dumps(tool_args)
                        )
                        tool_span.set_attribute("input.value", json.dumps(tool_args))
                        tool_span.set_attribute("input.mime_type", "application/json")

                        if tool_fn:
                            result = tool_fn(**tool_args)
                        else:
                            result = {
                                "status": "error",
                                "result": f"Unknown tool: {tool_name}",
                            }

                        tool_span.set_attribute("output.value", json.dumps(result))
                        tool_span.set_attribute("output.mime_type", "application/json")
                        tool_span.set_status(StatusCode.OK)

                    function_response_parts.append(
                        types.Part.from_function_response(
                            name=tool_name, response=result
                        )
                    )

                # Add function responses to history
                contents.append(
                    types.Content(role="user", parts=function_response_parts)
                )

            # Return final text response
            if response and response.candidates and response.candidates[0].content:
                result = "".join(
                    part.text
                    for part in response.candidates[0].content.parts
                    if part.text
                )
                span.set_attribute("output.value", result)
                span.set_attribute("output.mime_type", "text/plain")
                span.set_status(StatusCode.OK)
                return result

            span.set_attribute("output.value", "")
            span.set_attribute("output.mime_type", "text/plain")
            span.set_status(StatusCode.OK)
            return ""

    yield FunctionInfo.create(single_fn=_response_fn, description=config.description)
