import dbnl
import pandas as pd
import json


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

    df = dbnl.flatten_otlp_traces_data(raw_spans)

    # Extract trace_id from first span of each grouped trace
    dbnl_spans = dbnl.convert_otlp_traces_data(raw_spans)
    df["trace_id"] = [spans[0]["trace_id"] for spans in dbnl_spans]

    return df
