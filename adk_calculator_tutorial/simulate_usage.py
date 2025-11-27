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

from agent import get_agent

# Suppress warnings about non-text parts in responses
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

root_agent = get_agent()

USER_ID = "test-user"
session_service = InMemorySessionService()

# Create runner - let it auto-manage sessions
runner = Runner(
    agent=root_agent, app_name=root_agent.name, session_service=session_service
)


# Agent Interaction
async def call_agent(query, session_id):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    events = runner.run(user_id=USER_ID, session_id=session_id, new_message=content)
    for event in events:
        pass


def create_math_str(min=1, max=100):
    math_str = str(random.randint(min, max))
    math_str += random.choice(["+", "-", "*", "/"])
    math_str += str(random.randint(min, max))
    return math_str


async def main(max_traces, max_traces_per_session):
    total_traces_complete = 0
    while total_traces_complete < max_traces:
        # Create a session explicitly first
        session = await session_service.create_session(
            user_id=USER_ID, app_name=root_agent.name
        )

        for _ in range(random.randint(1, max_traces_per_session)):
            await call_agent(create_math_str(), session.id)
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
        default=1,
        help="Maximum traces per session (default: 1)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.max_traces, args.max_traces_per_session))
