import dbnl
import pandas as pd
import json
from collections import defaultdict


def group_resource_spans_by_trace_id(raw_spans_series):
    """
    raw_spans_series: pandas Series or any iterable of dicts like:
        {"resourceSpans": [ { "resource": ..., "scopeSpans": [...] }, ... ]}

    Returns:
        dict[trace_id] -> {"resourceSpans": [...]}
    """
    # trace_id -> ( (resource_key, scope_key) -> scopeSpanInfo )
    grouped = defaultdict(lambda: {})

    for payload in raw_spans_series:
        for rs in payload.get("resourceSpans", []):
            resource = rs.get("resource", {})
            resource_key = json.dumps(resource, sort_keys=True)

            for ss in rs.get("scopeSpans", []):
                scope = ss.get("scope", {})
                scope_key = json.dumps(scope, sort_keys=True)

                for span in ss.get("spans", []):
                    trace_id = span.get("traceId")
                    if trace_id is None:
                        continue

                    # For each trace_id, maintain resource+scope buckets
                    trace_bucket = grouped[trace_id]
                    rs_scope_key = (resource_key, scope_key)

                    if rs_scope_key not in trace_bucket:
                        trace_bucket[rs_scope_key] = {
                            "resource": resource,
                            "scope": scope,
                            "spans": [],
                        }

                    trace_bucket[rs_scope_key]["spans"].append(span)

    # Build final OTLP-style structures
    traces_by_id = {}

    for trace_id, rs_scope_map in grouped.items():
        resourceSpans = []

        # rs_scope_map: (resource_key, scope_key) -> {resource, scope, spans}
        # We need to group by resource, then within each, group by scope
        by_resource = defaultdict(list)
        for (_res_key, _scope_key), info in rs_scope_map.items():
            by_resource[json.dumps(info["resource"], sort_keys=True)].append(info)

        for _res_key, scope_infos in by_resource.items():
            # For each distinct resource, collect its scopeSpans
            scopeSpans = []
            # group by scope to keep shape scope + spans[]
            by_scope = defaultdict(list)
            for info in scope_infos:
                by_scope[json.dumps(info["scope"], sort_keys=True)].extend(
                    info["spans"]
                )

            for scope_json, spans in by_scope.items():
                scope = json.loads(scope_json)
                scopeSpans.append(
                    {
                        "scope": scope,
                        "spans": spans,
                    }
                )

            # All scopeSpans share the same resource
            resource = json.loads(_res_key)
            resourceSpans.append(
                {
                    "resource": resource,
                    "scopeSpans": scopeSpans,
                }
            )

        traces_by_id[trace_id] = {"resourceSpans": resourceSpans}

    return traces_by_id


def get_from_attrs(attrs, key):
    if attrs is None or (isinstance(attrs, float) and pd.isna(attrs)):
        return None

    # Case 1: simple dict: {"input.value": "...", ...}
    if isinstance(attrs, dict):
        return attrs.get(key)

    # Case 2: list[...] – could be dicts or tuples
    if isinstance(attrs, list):
        for item in attrs:
            # list of dicts like {"key": "...", "value": {"stringValue": "..."}}
            if isinstance(item, dict):
                if item.get("key") == key:
                    val = item.get("value")
                    if isinstance(val, dict) and "stringValue" in val:
                        return val["stringValue"]
                    return val
            # list of tuples like ("input.value", "…")
            elif isinstance(item, tuple) and len(item) >= 2:
                if item[0] == key:
                    return item[1]

    return None


def dbnl_df_from_otel_file(path, scope_filter="nat_calculator"):
    """
    Load OTEL traces from a JSONL file and convert to DBNL dataframe.

    Args:
        path: Path to the JSONL file containing OTEL traces
        scope_filter: Only include traces that have spans from this scope (default: "nat_calculator").
                     The traces_data will include ALL spans sharing the same trace_id,
                     including child spans from other scopes (e.g., GenerateContent from OpenInference).
                     Set to None to include all traces.
    """
    with open(path, "r") as f:
        all_raw_spans = pd.Series([json.loads(line) for line in f])

    if len(all_raw_spans) == 0:
        return pd.DataFrame(
            columns=["trace_id", "input", "output", "timestamp", "traces_data"]
        )

    # First, find trace_ids that have spans from the filtered scope
    if scope_filter:
        filtered_trace_ids = set()
        for payload in all_raw_spans:
            for rs in payload.get("resourceSpans", []):
                for ss in rs.get("scopeSpans", []):
                    scope = ss.get("scope", {})
                    if scope.get("name") == scope_filter:
                        for span in ss.get("spans", []):
                            filtered_trace_ids.add(span.get("traceId"))

        if not filtered_trace_ids:
            return pd.DataFrame(
                columns=["trace_id", "input", "output", "timestamp", "traces_data"]
            )

        # Filter to include ALL spans for matching trace_ids (includes child spans from other scopes)
        filtered_spans = []
        for payload in all_raw_spans:
            filtered_resource_spans = []
            for rs in payload.get("resourceSpans", []):
                filtered_scope_spans = []
                for ss in rs.get("scopeSpans", []):
                    filtered_span_list = [
                        span
                        for span in ss.get("spans", [])
                        if span.get("traceId") in filtered_trace_ids
                    ]
                    if filtered_span_list:
                        filtered_scope_spans.append(
                            {
                                "scope": ss.get("scope", {}),
                                "spans": filtered_span_list,
                            }
                        )
                if filtered_scope_spans:
                    filtered_resource_spans.append(
                        {
                            "resource": rs.get("resource", {}),
                            "scopeSpans": filtered_scope_spans,
                        }
                    )
            if filtered_resource_spans:
                filtered_spans.append({"resourceSpans": filtered_resource_spans})
        raw_spans = (
            pd.Series(filtered_spans) if filtered_spans else pd.Series([], dtype=object)
        )
    else:
        raw_spans = all_raw_spans

    if len(raw_spans) == 0:
        return pd.DataFrame(
            columns=["trace_id", "input", "output", "timestamp", "traces_data"]
        )

    # For input/output extraction, only use spans from the filtered scope
    if scope_filter:
        scope_filtered_spans = []
        for payload in raw_spans:
            filtered_resource_spans = []
            for rs in payload.get("resourceSpans", []):
                filtered_scope_spans = []
                for ss in rs.get("scopeSpans", []):
                    scope = ss.get("scope", {})
                    if scope.get("name") == scope_filter:
                        filtered_scope_spans.append(ss)
                if filtered_scope_spans:
                    filtered_resource_spans.append(
                        {
                            "resource": rs.get("resource", {}),
                            "scopeSpans": filtered_scope_spans,
                        }
                    )
            if filtered_resource_spans:
                scope_filtered_spans.append({"resourceSpans": filtered_resource_spans})
        scope_filtered_raw = (
            pd.Series(scope_filtered_spans)
            if scope_filtered_spans
            else pd.Series([], dtype=object)
        )
    else:
        scope_filtered_raw = raw_spans

    dbnl_spans = dbnl.convert_otlp_traces_data(data=scope_filtered_raw)
    spans_df = pd.DataFrame(dbnl_spans.explode().tolist())
    grouped_traces = spans_df.groupby("trace_id", dropna=False)

    # earliest start_time per trace
    timestamps = grouped_traces["start_time"].min().rename("timestamp")

    # input: find the calculator_agent span's input.value
    def get_input_from_trace(g):
        for _, row in g.iterrows():
            if row.get("name") == "calculator_agent":
                val = get_from_attrs(row["attributes"], "input.value")
                if val is not None:
                    return val
        return None

    # output: find the calculator_agent span's output.value
    def get_output_from_trace(g):
        for _, row in g.iterrows():
            if row.get("name") == "calculator_agent":
                val = get_from_attrs(row["attributes"], "output.value")
                if val is not None:
                    return val
        return None

    inputs = grouped_traces.apply(get_input_from_trace, include_groups=False)
    inputs.name = "input"

    outputs = grouped_traces.apply(get_output_from_trace, include_groups=False)
    outputs.name = "output"

    # traces_data includes ALL spans for the trace (including child spans from other scopes)
    traces_by_id = group_resource_spans_by_trace_id(raw_spans)

    dbnl_df = pd.concat([inputs, outputs, timestamps], axis=1).reset_index()
    dbnl_df["traces_data"] = dbnl_df["trace_id"].map(traces_by_id)

    return dbnl_df
