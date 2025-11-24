"""Script to run the calculator agent and generate trace data."""

import argparse
import asyncio
import logging
import os
import random
import sys
import time

# Add parent directory to path so we can import the agent module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from ab_test_example.agent_v0 import get_agent_v0
from ab_test_example.agent_v1 import get_agent_v1

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from openinference.instrumentation.google_adk import GoogleADKInstrumentor

provider = TracerProvider()
trace.set_tracer_provider(provider)

exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318/v1/traces",  # matches your otelcol http receiver
)

processor = SimpleSpanProcessor(exporter)
provider.add_span_processor(processor)

GoogleADKInstrumentor().instrument(tracer_provider=provider)

# Suppress warnings about non-text parts in responses
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

USER_ID = "test-user"


def create_math_str(length=None, min=1, max=100):
    if not length:
        length = random.randint(2, 3)
    math_str = str(random.randint(min, max))
    for _ in range(length - 1):
        math_str += random.choice(["+", "-", "*", "/"])
        math_str += str(random.randint(min, max))
    return math_str


# Agent Interaction
async def call_agent(query, session_id, runner, app_name):
    content = types.Content(role="user", parts=[types.Part(text=query)])

    events = runner.run(
        user_id=USER_ID,
        session_id=session_id,
        new_message=content,
    )

    for event in events:
        span = trace.get_current_span()
        if span is not None:
            span.set_attribute("app.name", "app_name")


async def main(max_traces, max_traces_per_session, version_split):
    root_agent_v0 = get_agent_v0()
    root_agent_v1 = get_agent_v1()

    session_service = InMemorySessionService()

    # Create runner - let it auto-manage sessions
    runner_v0 = Runner(
        agent=root_agent_v0,
        app_name=root_agent_v0.name,
        session_service=session_service,
    )
    runner_v1 = Runner(
        agent=root_agent_v1,
        app_name=root_agent_v1.name,
        session_service=session_service,
    )

    total_traces_complete = 0
    while total_traces_complete < max_traces:
        if random.random() < version_split["v0"]:
            app_name = root_agent_v0.name
            runner = runner_v0
        else:
            app_name = root_agent_v1.name
            runner = runner_v1

        # Create a session explicitly first
        session = await session_service.create_session(
            user_id=USER_ID, app_name=app_name
        )

        for _ in range(random.randint(1, max_traces_per_session)):
            await call_agent(create_math_str(), session.id, runner, app_name)
            total_traces_complete += 1
            if total_traces_complete >= max_traces:
                break

        time.sleep(random.randint(1, 3))
        print(f"{total_traces_complete}/{max_traces} traces.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the calculator agent and generate trace data."
    )
    parser.add_argument(
        "--max-traces",
        type=int,
        default=5,
        help="Maximum number of traces to generate (default: 5)",
    )
    parser.add_argument(
        "--max-traces-per-session",
        type=int,
        default=2,
        help="Maximum traces per session (default: 2)",
    )
    parser.add_argument(
        "--version_split_ratio",
        type=float,
        default=1.0,
        help="The percentage of traces that will be generated using agent_v0 (vs agent_v1)",
    )
    args = parser.parse_args()

    version_split = {
        "v0": args.version_split_ratio,
        "v1": 1 - args.version_split_ratio,
    }

    asyncio.run(main(args.max_traces, args.max_traces_per_session, version_split))
