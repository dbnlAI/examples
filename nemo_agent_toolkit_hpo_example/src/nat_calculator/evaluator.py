# SPDX-FileCopyrightText: Copyright (c) 2025
# SPDX-License-Identifier: Apache-2.0

"""Custom math evaluator for the calculator agent."""

import logging
import re

from nat.builder.builder import EvalBuilder
from nat.builder.evaluator import EvaluatorInfo
from nat.cli.register_workflow import register_evaluator
from nat.data_models.evaluator import EvaluatorBaseConfig
from nat.eval.evaluator.evaluator_model import EvalInput, EvalOutput, EvalOutputItem

logger = logging.getLogger(__name__)


class MathAbsoluteErrorConfig(EvaluatorBaseConfig, name="math_absolute_error"):
    """Configuration for the math absolute error evaluator."""

    pass


@register_evaluator(config_type=MathAbsoluteErrorConfig)
async def register_math_absolute_error_evaluator(
    config: MathAbsoluteErrorConfig, builder: EvalBuilder
):
    """Register the math absolute error evaluator."""

    async def evaluate_fn(eval_input: EvalInput) -> EvalOutput:
        """
        Evaluates math accuracy by computing the absolute error between
        the agent's response and the expected answer.

        Returns the absolute error as the score (lower is better, minimize this).
        """
        eval_output_items = []
        total_error = 0.0
        count = 0

        for item in eval_input.eval_input_items:
            # input_obj is the question, output_obj is the agent response
            # expected_output_obj is the ground truth
            question = str(item.input_obj) if item.input_obj else ""
            agent_response = str(item.output_obj) if item.output_obj else ""
            ground_truth = (
                str(item.expected_output_obj) if item.expected_output_obj else ""
            )

            # Extract numeric value from agent response
            agent_value = extract_number(agent_response)

            # Get expected value from ground truth
            if ground_truth:
                expected_value = extract_number(ground_truth)
            else:
                expected_value = evaluate_math_expression(question)

            if agent_value is None:
                logger.warning(
                    f"Could not extract number from agent response: {agent_response}"
                )
                error = 1000.0
                reason = f"Could not extract number from response: {agent_response}"
            elif expected_value is None:
                logger.warning(
                    f"Could not determine expected value for question: {question}"
                )
                error = 1000.0
                reason = f"Could not determine expected value for: {question}"
            else:
                error = abs(agent_value - expected_value)
                reason = (
                    f"Agent: {agent_value}, Expected: {expected_value}, Error: {error}"
                )

            eval_output_items.append(
                EvalOutputItem(id=item.id, score=error, reasoning=reason)
            )
            total_error += error
            count += 1

        avg_error = total_error / count if count > 0 else 1000.0

        return EvalOutput(average_score=avg_error, eval_output_items=eval_output_items)

    yield EvaluatorInfo(
        config=config,
        evaluate_fn=evaluate_fn,
        description="Average absolute error between agent response and expected answer",
    )


def extract_number(text: str) -> float | None:
    """Extract the first number from a text string."""
    if text is None:
        return None

    # Try to find a number (including negative and decimal)
    match = re.search(r"-?\d+\.?\d*", str(text))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def evaluate_math_expression(question: str) -> float | None:
    """Try to extract and evaluate a math expression from the question."""
    # Common patterns for math questions
    # "What is 5 + 3?" -> "5 + 3"
    # "Calculate 25 + 17" -> "25 + 17"
    # "8+2" -> "8+2"

    # Extract potential math expression
    # Remove common question words
    cleaned = question.lower()
    for word in ["what is", "calculate", "compute", "evaluate", "solve", "?"]:
        cleaned = cleaned.replace(word, "")

    # Handle word forms
    cleaned = cleaned.replace("plus", "+")
    cleaned = cleaned.replace("minus", "-")
    cleaned = cleaned.replace("times", "*")
    cleaned = cleaned.replace("multiplied by", "*")
    cleaned = cleaned.replace("divided by", "/")
    cleaned = cleaned.replace("x", "*")
    cleaned = cleaned.replace("from", "")
    cleaned = cleaned.replace("subtract", "")
    cleaned = cleaned.replace("multiply", "")
    cleaned = cleaned.replace("divide", "")
    cleaned = cleaned.replace("add", "")
    cleaned = cleaned.replace("by", "")

    cleaned = cleaned.strip()

    # Try to evaluate the expression safely
    try:
        # Only allow digits, operators, spaces, and decimal points
        if re.match(r"^[\d\s\+\-\*\/\.\(\)]+$", cleaned):
            result = eval(cleaned)
            return float(result)
    except Exception:
        pass

    return None
