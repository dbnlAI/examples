# SPDX-FileCopyrightText: Copyright (c) 2025
# SPDX-License-Identifier: Apache-2.0

"""Calculator tools for NeMo Agent Toolkit."""

from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig


class AddConfig(FunctionBaseConfig, name="add"):
    """Configuration for the add tool."""

    description: str = "Returns the sum of two numbers by adding them together"


class SubtractConfig(FunctionBaseConfig, name="subtract"):
    """Configuration for the subtract tool."""

    description: str = (
        "Returns the result of subtracting the second number from the first number"
    )


class MultiplyConfig(FunctionBaseConfig, name="multiply"):
    """Configuration for the multiply tool."""

    description: str = "Returns the product of multiplying two numbers together"


class DivideConfig(FunctionBaseConfig, name="divide"):
    """Configuration for the divide tool."""

    description: str = (
        "Returns the result of dividing the first number by the second number"
    )


@register_function(config_type=AddConfig)
async def add_tool(config: AddConfig, builder):
    """Add two numbers together."""
    from nat.builder.function_info import FunctionInfo

    def add_two_numbers(a: float, b: float) -> dict:
        """Returns the sum of two numbers by adding them together"""
        return {"status": "ok", "result": a + b}

    yield FunctionInfo.create(single_fn=add_two_numbers, description=config.description)


@register_function(config_type=SubtractConfig)
async def subtract_tool(config: SubtractConfig, builder):
    """Subtract two numbers."""
    from nat.builder.function_info import FunctionInfo

    def subtract_two_numbers(a: float, b: float) -> dict:
        """Returns the result of subtracting the second number from the first number"""
        return {"status": "ok", "result": a - b}

    yield FunctionInfo.create(
        single_fn=subtract_two_numbers, description=config.description
    )


@register_function(config_type=MultiplyConfig)
async def multiply_tool(config: MultiplyConfig, builder):
    """Multiply two numbers."""
    from nat.builder.function_info import FunctionInfo

    def multiply_two_numbers(a: float, b: float) -> dict:
        """Returns the product of multiplying two numbers together"""
        return {"status": "ok", "result": a * b}

    yield FunctionInfo.create(
        single_fn=multiply_two_numbers, description=config.description
    )


@register_function(config_type=DivideConfig)
async def divide_tool(config: DivideConfig, builder):
    """Divide two numbers."""
    from nat.builder.function_info import FunctionInfo

    def divide_two_numbers(a: float, b: float) -> dict:
        """Returns the result of dividing the first number by the second number"""
        if b == 0:
            return {"status": "error", "result": "Cannot divide by zero"}
        return {"status": "ok", "result": a / b}

    yield FunctionInfo.create(
        single_fn=divide_two_numbers, description=config.description
    )
