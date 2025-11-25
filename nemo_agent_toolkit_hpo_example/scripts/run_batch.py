#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025
# SPDX-License-Identifier: Apache-2.0

"""Run NAT workflow against a batch of inputs, generating traces for each."""

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add parent to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nat.runtime.loader import load_config
from nat.builder.workflow_builder import WorkflowBuilder
from nat.runtime.session import SessionManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def run_batch(config_file: str, input_file: str, limit: int | None = None):
    """Run workflow against each input in the file."""

    # Load inputs
    with open(input_file) as f:
        inputs = json.load(f)

    if limit:
        inputs = inputs[:limit]

    logger.info(f"Loaded {len(inputs)} inputs from {input_file}")

    # Load config and build workflow
    config = load_config(config_file)

    async with WorkflowBuilder.from_config(config=config) as builder:
        workflow = await builder.build()
        session_manager = SessionManager(workflow, max_concurrency=1)

        results = []
        for i, question in enumerate(inputs):
            logger.info(f"[{i+1}/{len(inputs)}] Processing: {question[:50]}...")

            try:
                async with session_manager.run(question) as runner:
                    result = await runner.result()
                    # Convert to string if needed
                    result_str = runner.convert(result, to_type=str)
                    results.append({"question": question, "answer": result_str})
                    logger.info(f"[{i+1}/{len(inputs)}] Result: {result_str}")
            except Exception as e:
                logger.error(f"[{i+1}/{len(inputs)}] Error: {e}")
                results.append({"question": question, "error": str(e)})

            time.sleep(2)  # don't flood gemini

        logger.info(f"Completed {len(results)} questions")
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Run NAT workflow against batch inputs"
    )
    parser.add_argument("--config_file", required=True, help="Path to NAT config YAML")
    parser.add_argument(
        "--input_file", required=True, help="Path to JSON file with list of inputs"
    )
    parser.add_argument("--limit", type=int, help="Limit number of inputs to process")
    parser.add_argument("--output_file", help="Path to save results JSON")

    args = parser.parse_args()

    results = asyncio.run(run_batch(args.config_file, args.input_file, args.limit))

    # Flush OpenInference spans
    from opentelemetry import trace

    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()
        logger.info("Flushed OpenTelemetry spans")

    if args.output_file:
        with open(args.output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {args.output_file}")


if __name__ == "__main__":
    main()
