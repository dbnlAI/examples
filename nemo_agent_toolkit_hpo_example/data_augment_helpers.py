import re
import pandas as pd
import random
import json

# Short messages (customize as you like)
complaints = [
    "That’s not right!",
    "Wrong result again!",
    "Calculator failed.",
    "Off by a mile.",
    "Bad math output!",
    "Totally incorrect!",
    "Oops, wrong calc.",
    "Computation error.",
    "Answer is wrong.",
    "Incorrect result.",
    "Math seems broken.",
    "Calculation flaw.",
    "Miscalculated that.",
    "Wrong total shown.",
    "Completely off!",
    "This seems buggy.",
    "Bad arithmetic!",
    "The math is wrong.",
    "Way off the mark.",
    "Error in result!",
]
praises = [
    "Perfect result!",
    "Nice work!",
    "Correct again!",
    "Spot on!",
    "You nailed it!",
    "Looks good!",
    "Math checks out!",
    "Well done!",
    "Accurate answer!",
    "Exactly right!",
    "All good here!",
    "Bang on target!",
    "That’s correct!",
    "Great calculation!",
    "Awesome result!",
    "Nice precision!",
    "Flawless math!",
    "Right on point!",
    "Excellent job!",
    "Spotless result!",
]

COST = {  # per token (Gemini 2.5 Flash pricing)
    "llm.token_count.prompt": 0.000000075,
    "llm.token_count.completion": 0.00000030,
}


def est_cost_from_llm_tokens(traces_data):
    """
    Estimate cost from llm.token_count.prompt and llm.token_count.completion across all LLM spans.

    Args:
        traces_data: OTEL traces data dict with structure:
            {"resourceSpans": [{"scopeSpans": [{"spans": [...]}]}]}

    Returns:
        Estimated cost in dollars based on token counts.
    """
    if traces_data is None:
        return 0

    total = 0
    for rs in traces_data.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                attrs = span.get("attributes", [])
                # attrs is a list of dicts: [{"key": "...", "value": {"intValue": "..."}}]
                for attr in attrs:
                    key = attr.get("key", "")
                    if key in COST:
                        val = attr.get("value", {})
                        # Token counts use intValue
                        int_val = val.get("intValue")
                        if int_val is not None:
                            try:
                                total += int(int_val) * COST[key]
                            except (ValueError, TypeError):
                                pass
    return total


def compute_feedback(row, p_keep=0.11):
    # 89% chance to leave both None
    if random.random() > p_keep:
        return pd.Series({"feedback_score": None, "feedback_text": None})

    out = float(json.loads(row["output"]))
    exp = float(row["output_expected"])

    if out is not None and exp is not None and out == exp:
        score = 5
        text = random.choice(praises)
    else:
        score = 1
        text = random.choice(complaints)

    # JSON-safe primitives
    return pd.Series({"feedback_score": int(score), "feedback_text": str(text)})


def compute_abs_error(row):
    out = float(json.loads(row["output"]))
    exp = float(row["output_expected"])

    return abs(out - exp)


def compute_expected_answer(question: str) -> float | None:
    """
    Parse a math question and compute the expected answer.

    Handles various question formats like:
    - "What is 3 plus 94?"
    - "What is 94 - 13?"
    - "Calculate 76 / 76"
    - "Compute 81 / 49"
    - "10 * 29 = ?"
    - "Sum of 19 and 80?"
    - "Product of 30 and 7?"
    - "Subtract 93 from 68"
    - "Add 65 and 30"
    - "Multiply 98 by 82"
    - "Divide 86 by 43"
    - "72 take away 91?"
    - "68 over 50?"

    Returns:
        The computed answer as a float, or None if the question couldn't be parsed.
    """
    question = question.lower().strip()

    # Patterns for different question formats
    patterns = [
        # "What is X plus/minus/times/divided by Y"
        (
            r"what is (\d+(?:\.\d+)?)\s*(plus|\+|minus|-|times|\*|divided by|/)\s*(\d+(?:\.\d+)?)",
            None,
        ),
        # "Calculate/Compute X op Y"
        (
            r"(?:calculate|compute)\s+(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)",
            None,
        ),
        # "X op Y = ?"
        (r"(\d+(?:\.\d+)?)\s*([+\-*/])\s*(\d+(?:\.\d+)?)\s*=", None),
        # "Sum of X and Y"
        (r"sum of (\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", "+"),
        # "Product of X and Y"
        (r"product of (\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", "*"),
        # "Subtract Y from X" (result is X - Y)
        (r"subtract (\d+(?:\.\d+)?)\s+from\s+(\d+(?:\.\d+)?)", "subtract_from"),
        # "Add X and Y"
        (r"add (\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", "+"),
        # "Multiply X by Y"
        (r"multiply (\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)", "*"),
        # "Divide X by Y"
        (r"divide (\d+(?:\.\d+)?)\s+by\s+(\d+(?:\.\d+)?)", "/"),
        # "X take away Y"
        (r"(\d+(?:\.\d+)?)\s+take away\s+(\d+(?:\.\d+)?)", "-"),
        # "X over Y"
        (r"(\d+(?:\.\d+)?)\s+over\s+(\d+(?:\.\d+)?)", "/"),
        # "X plus/minus/times/divided by Y" (without "what is")
        (
            r"(\d+(?:\.\d+)?)\s*(plus|\+|minus|-|times|\*|divided by|/)\s*(\d+(?:\.\d+)?)",
            None,
        ),
    ]

    for pattern, fixed_op in patterns:
        match = re.search(pattern, question)
        if match:
            groups = match.groups()

            if fixed_op == "subtract_from":
                # "Subtract Y from X" means X - Y, but groups are (Y, X)
                a = float(groups[1])
                b = float(groups[0])
                return a - b
            elif fixed_op:
                a = float(groups[0])
                b = float(groups[1])
                op = fixed_op
            else:
                a = float(groups[0])
                op = groups[1]
                b = float(groups[2])

            # Normalize operator
            op = op.lower().strip()
            if op in ("plus", "+"):
                return a + b
            elif op in ("minus", "-"):
                return a - b
            elif op in ("times", "*"):
                return a * b
            elif op in ("divided by", "/", "over"):
                if b == 0:
                    return None
                return a / b

    return None
