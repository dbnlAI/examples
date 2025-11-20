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
                by_scope[json.dumps(info["scope"], sort_keys=True)].extend(info["spans"])

            for scope_json, spans in by_scope.items():
                scope = json.loads(scope_json)
                scopeSpans.append({
                    "scope": scope,
                    "spans": spans,
                })

            # All scopeSpans share the same resource
            resource = json.loads(_res_key)
            resourceSpans.append({
                "resource": resource,
                "scopeSpans": scopeSpans,
            })

        traces_by_id[trace_id] = {
            "resourceSpans": resourceSpans
        }

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

def dbnl_df_from_otel_file(path):
    with open(path, "r") as f:
        raw_spans = pd.Series([json.loads(line) for line in f])

    dbnl_spans = dbnl.convert_otlp_traces_data(data=raw_spans)
    spans_df = pd.DataFrame(dbnl_spans.explode().tolist())
    grouped_traces = spans_df.groupby("trace_id", dropna=False)

    # earliest start_time per trace
    timestamps = grouped_traces["start_time"].min().rename("timestamp")

    # input: from FIRST span's attributes
    inputs = grouped_traces.apply(
        lambda g: get_from_attrs(
            g.sort_values("start_time").iloc[0]["attributes"],
            "input.value"
        ),
        include_groups=False,
    ).rename("input")

    # output: from LAST span's attributes
    outputs = grouped_traces.apply(
        lambda g: get_from_attrs(
            g.sort_values("end_time").iloc[-1]["attributes"],
            "output.value"
        ),
        include_groups=False,
    ).rename("output")

    traces_by_id = group_resource_spans_by_trace_id(raw_spans)

    dbnl_df = pd.concat([inputs, outputs, timestamps], axis=1).reset_index()
    dbnl_df["traces_data"] = dbnl_df["trace_id"].map(traces_by_id)

    return dbnl_df
