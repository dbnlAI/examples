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

complaints = [
    "This calculator keeps giving me the wrong result!",
    "That’s not the right answer at all. I’m annoyed!",
    "Why does this calculator mess up simple math?",
    "The answer is completely wrong. So frustrating!",
    "I can’t believe it got the math wrong again!",
    "Something’s off — that’s definitely not correct.",
    "It’s giving me errors for basic calculations!",
    "The math is wrong, this calculator is broken!",
    "That’s not what I expected — check your math!",
    "Wrong result again! This is driving me crazy.",
    "How can it get this wrong? What’s happening?",
    "There must be a bug — the answer is nonsense.",
    "This calculator is totally unreliable, wrong again!",
    "Frustrating! It keeps giving the wrong answers.",
    "That’s clearly not the right calculation result.",
    "Ugh, another wrong answer — please fix this bug!",
    "Even simple math gives bad results. Annoying!",
    "It’s calculating wrong again — I’m losing patience!",
    "Something’s broken here. That result makes no sense.",
    "I’m sure the answer’s wrong. This calculator fails!",
]

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
    output = ""
    for event in events:
        try:
            output = event.content.parts[0].text
        except (AttributeError, IndexError, TypeError):
            output = ""

    try:
        correct = float(eval(query)) == float(output)
    except (ValueError, SyntaxError, TypeError):
        correct = False

    if not correct:
        # Send complaint to the agent
        content = types.Content(
            role="user", parts=[types.Part(text=random.choice(complaints))]
        )
        events = runner.run(user_id=USER_ID, session_id=session_id, new_message=content)
        # Consume events
        for event in events:
            pass


def create_math_str(length=None, min=1, max=100):
    if not length:
        length = random.randint(2, 3)
    math_str = str(random.randint(min, max))
    for _ in range(length - 1):
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
        default=2,
        help="Maximum traces per session (default: 2)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.max_traces, args.max_traces_per_session))
