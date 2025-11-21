#!/usr/bin/env python3
"""
Convert Langfuse export files to DBNL format.

This script transforms Langfuse trace and observation exports into the DBNL
semantic convention format, which can be readily loaded into a pandas DataFrame.

Usage:
    python langfuse_to_dbnl.py --traces lf-traces-export.jsonl --observations lf-observations-export.jsonl --output traces.jsonl
"""

import json
import argparse
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any


def parse_json_field(field: Any) -> Any:
    """Parse a field that might be a JSON string or already parsed."""
    if isinstance(field, str):
        try:
            return json.loads(field)
        except json.JSONDecodeError:
            return field
    return field


def extract_attributes(metadata: Dict) -> Dict[str, Any]:
    """Extract attributes from metadata, handling JSON strings."""
    if not metadata:
        return {}

    # Parse attributes if it's a JSON string
    attributes = metadata.get("attributes", {})
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except json.JSONDecodeError:
            attributes = {}

    return attributes if isinstance(attributes, dict) else {}


def convert_observation_to_span(obs: Dict) -> Dict[str, Any]:
    """Convert a Langfuse observation to a DBNL span."""
    attributes = extract_attributes(obs.get("metadata", {}))

    # Build attributes list as key-value pairs
    attr_list = []
    for key, value in attributes.items():
        # Convert value to string representation, then JSON-escape it
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        # JSON-escape the string value for safety
        value_str = json.dumps(value_str)

        attr_list.append({"key": key, "value": value_str})

    # Add input.value if input exists
    if obs.get("input") is not None:
        input_value = obs["input"]
        if isinstance(input_value, (dict, list)):
            input_str = json.dumps(input_value)
        else:
            input_str = str(input_value)

        # JSON-escape the string value
        input_str = json.dumps(input_str)

        attr_list.append({"key": "input.value", "value": input_str})

    # Add output.value if output exists
    if obs.get("output") is not None:
        output_value = obs["output"]
        if isinstance(output_value, (dict, list)):
            output_str = json.dumps(output_value)
        else:
            output_str = str(output_value)

        # JSON-escape the string value
        output_str = json.dumps(output_str)

        attr_list.append({"key": "output.value", "value": output_str})

    # Determine span kind from type and attributes
    span_kind = obs.get("type", "UNKNOWN")
    if "openinference.span.kind" in attributes:
        span_kind = attributes["openinference.span.kind"]

    # Build the span (ensure no None values)
    span = {
        "trace_id": str(obs.get("traceId", "")),
        "span_id": str(obs.get("id", "")),
        "trace_state": "",
        "parent_span_id": str(obs.get("parentObservationId", "")),
        "name": str(obs.get("name", "")),
        "kind": str(span_kind),
        "start_time": str(obs.get("startTime", "")),
        "end_time": str(obs.get("endTime", "")),
        "attributes": attr_list,
        "events": [],
        "links": [],
        "status": {
            "code": "ERROR"
            if obs.get("level") == "ERROR" or obs.get("statusMessage")
            else "OK",
            "message": str(obs.get("statusMessage", "")),
        },
    }

    return span


def aggregate_trace_metrics(observations: List[Dict]) -> Dict[str, Any]:
    """Aggregate metrics from observations for a trace."""
    metrics = {
        "total_token_count": 0,
        "prompt_token_count": 0,
        "completion_token_count": 0,
        "total_cost": 0.0,
        "prompt_cost": 0.0,
        "completion_cost": 0.0,
        "tool_call_count": 0,
        "tool_call_error_count": 0,
        "tool_call_name_counts": defaultdict(int),
        "llm_call_count": 0,
        "llm_call_error_count": 0,
        "llm_call_model_counts": defaultdict(int),
        "call_sequence": [],
        "duration_ms": 0,
        "status": "OK",
        "status_message": "",
    }

    # Sort observations by startTime to build proper call sequence
    sorted_obs = sorted(observations, key=lambda x: x.get("startTime", ""))

    for obs in sorted_obs:
        obs_type = obs.get("type", "")
        attributes = extract_attributes(obs.get("metadata", {}))

        # Calculate duration
        if obs.get("startTime") and obs.get("endTime"):
            start = datetime.fromisoformat(obs["startTime"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(obs["endTime"].replace("Z", "+00:00"))
            duration = int((end - start).total_seconds() * 1000)
            metrics["duration_ms"] = max(metrics["duration_ms"], duration)

        # Check for errors
        if obs.get("statusMessage") or obs.get("level") == "ERROR":
            metrics["status"] = "ERROR"
            if obs.get("statusMessage"):
                metrics["status_message"] = str(obs["statusMessage"])

        # Handle LLM observations (GENERATION type)
        if obs_type == "GENERATION" or span_kind_is_llm(attributes):
            metrics["llm_call_count"] += 1

            # Get model name from various possible locations
            model_name = (
                obs.get("model")
                or obs.get("modelId")
                or attributes.get("llm.model_name")
                or attributes.get("gen_ai.request.model")
                or "unknown"
            )
            metrics["llm_call_model_counts"][model_name] += 1

            # Add to call sequence
            metrics["call_sequence"].append(f"llm:{model_name}")

            # Aggregate token counts from observation-level fields
            input_usage = obs.get("inputUsage", 0) or 0
            output_usage = obs.get("outputUsage", 0) or 0
            total_usage = obs.get("totalUsage", 0) or 0

            metrics["prompt_token_count"] += input_usage
            metrics["completion_token_count"] += output_usage
            metrics["total_token_count"] += total_usage

            # Aggregate costs from observation-level fields
            input_cost = obs.get("inputCost", 0) or 0
            output_cost = obs.get("outputCost", 0) or 0
            total_cost = obs.get("totalCost", 0) or 0

            metrics["prompt_cost"] += input_cost
            metrics["completion_cost"] += output_cost
            metrics["total_cost"] += total_cost

            # Check for LLM errors
            if obs.get("statusMessage"):
                metrics["llm_call_error_count"] += 1

        # Handle TOOL observations (EVENT type or TOOL span kind)
        elif obs_type == "EVENT" or span_kind_is_tool(attributes):
            metrics["tool_call_count"] += 1

            # Get tool name from attributes or observation name
            tool_name = attributes.get("tool.name") or obs.get("name", "unknown")

            # Clean up tool name if it has prefixes
            if tool_name.startswith("execute_tool "):
                tool_name = tool_name.replace("execute_tool ", "")

            metrics["tool_call_name_counts"][tool_name] += 1

            # Add to call sequence
            metrics["call_sequence"].append(f"tool:{tool_name}")

            # Check for tool errors
            if obs.get("statusMessage") or obs.get("level") == "ERROR":
                metrics["tool_call_error_count"] += 1

    # Convert defaultdicts to regular dicts
    metrics["tool_call_name_counts"] = dict(metrics["tool_call_name_counts"])
    metrics["llm_call_model_counts"] = dict(metrics["llm_call_model_counts"])

    return metrics


def span_kind_is_llm(attributes: Dict) -> bool:
    """Check if span kind indicates an LLM call."""
    span_kind = attributes.get("openinference.span.kind", "")
    return span_kind == "LLM"


def span_kind_is_tool(attributes: Dict) -> bool:
    """Check if span kind indicates a tool call."""
    span_kind = attributes.get("openinference.span.kind", "")
    return span_kind == "TOOL"


def deep_json_escape_value(value: Any) -> Any:
    """Recursively JSON-escape all strings inside a value (for input/output fields only)."""
    if isinstance(value, str):
        return json.dumps(value)

    if isinstance(value, list):
        return [deep_json_escape_value(v) for v in value]

    if isinstance(value, dict):
        return {k: deep_json_escape_value(v) for k, v in value.items()}

    return value


def convert_langfuse_to_dbnl(
    traces: List[Dict], observations: List[Dict]
) -> List[Dict]:
    """Convert Langfuse exports to DBNL format."""
    # Group observations by trace ID
    obs_by_trace = defaultdict(list)
    for obs in observations:
        trace_id = obs.get("traceId")
        if trace_id:
            obs_by_trace[trace_id].append(obs)

    dbnl_traces = []

    for trace in traces:
        trace_id = trace.get("id")
        if not trace_id:
            continue

        # Get observations for this trace
        trace_obs = obs_by_trace.get(trace_id, [])

        # Parse input and output
        trace_input = parse_json_field(trace.get("input", ""))
        trace_output = parse_json_field(trace.get("output", ""))

        # Convert to strings if they're dicts
        if isinstance(trace_input, dict):
            trace_input = json.dumps(trace_input)
        elif trace_input is None:
            trace_input = ""
        else:
            trace_input = str(trace_input)

        if isinstance(trace_output, dict):
            trace_output = json.dumps(trace_output)
        elif trace_output is None:
            trace_output = ""
        else:
            trace_output = str(trace_output)

        # Aggregate metrics from observations
        metrics = aggregate_trace_metrics(trace_obs)

        # Convert observations to spans
        spans = [convert_observation_to_span(obs) for obs in trace_obs]

        # Build DBNL trace with no None values (use empty strings instead)
        dbnl_trace = {
            "trace_id": str(trace_id),
            "session_id": str(trace.get("sessionId", "")),
            "input": trace_input,
            "output": trace_output,
            "timestamp": str(trace.get("timestamp", "")),
            "duration_ms": metrics["duration_ms"],
            "status": metrics["status"],
            "status_message": metrics["status_message"],
            "total_token_count": metrics["total_token_count"],
            "prompt_token_count": metrics["prompt_token_count"],
            "completion_token_count": metrics["completion_token_count"],
            "total_cost": metrics["total_cost"],
            "prompt_cost": metrics["prompt_cost"],
            "completion_cost": metrics["completion_cost"],
            "tool_call_count": metrics["tool_call_count"],
            "tool_call_error_count": metrics["tool_call_error_count"],
            "tool_call_name_counts": metrics["tool_call_name_counts"],
            "llm_call_count": metrics["llm_call_count"],
            "llm_call_error_count": metrics["llm_call_error_count"],
            "llm_call_model_counts": metrics["llm_call_model_counts"],
            "call_sequence": metrics["call_sequence"],
            "spans": spans,
        }

        # Add optional fields (use empty string if not present)
        dbnl_trace["user_id"] = str(trace.get("userId", ""))

        # Apply deep JSON escaping ONLY to input and output fields
        dbnl_trace["input"] = deep_json_escape_value(dbnl_trace["input"])
        dbnl_trace["output"] = deep_json_escape_value(dbnl_trace["output"])

        dbnl_traces.append(dbnl_trace)

    return dbnl_traces


def main():
    parser = argparse.ArgumentParser(
        description="Convert Langfuse export files to DBNL format"
    )
    parser.add_argument(
        "--traces",
        default="lf-traces-export.jsonl",
        help="Path to Langfuse traces export file (default: lf-traces-export.jsonl)",
    )
    parser.add_argument(
        "--observations",
        default="lf-observations-export.jsonl",
        help="Path to Langfuse observations export file (default: lf-observations-export.jsonl)",
    )
    parser.add_argument(
        "--output",
        default="traces.jsonl",
        help="Path to output DBNL traces file (default: traces.jsonl)",
    )

    args = parser.parse_args()

    # Read traces
    print(f"Reading traces from {args.traces}...")
    traces = []
    with open(args.traces, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                traces.append(json.loads(line))
    print(f"Loaded {len(traces)} traces")

    # Read observations
    print(f"Reading observations from {args.observations}...")
    observations = []
    with open(args.observations, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                observations.append(json.loads(line))
    print(f"Loaded {len(observations)} observations")

    # Convert to DBNL format
    print("Converting to DBNL format...")
    dbnl_traces = convert_langfuse_to_dbnl(traces, observations)
    print(f"Converted {len(dbnl_traces)} traces")

    # Write output
    print(f"Writing output to {args.output}...")
    with open(args.output, "w") as f:
        for trace in dbnl_traces:
            f.write(json.dumps(trace) + "\n")

    print(f"Successfully wrote {len(dbnl_traces)} traces to {args.output}")
    print("\nYou can now load the data into pandas:")
    print("  import pandas as pd")
    print(f"  df = pd.read_json('{args.output}', lines=True)")


if __name__ == "__main__":
    main()
