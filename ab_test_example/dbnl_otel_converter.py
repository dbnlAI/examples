import dbnl
import pandas as pd
import json


def inject_root_span_attrs(otlp_dict, attrs):
    """Inject custom key-value pairs into the root span's attributes in place."""
    for rs in otlp_dict.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                if not span.get("parentSpanId"):  # root span has no parent
                    span_attrs = span.setdefault("attributes", [])
                    for key, val in attrs.items():
                        if val is None or val != val:  # None or NaN
                            continue
                        if isinstance(val, str):
                            span_attrs.append({"key": key, "value": {"stringValue": val}})
                        elif isinstance(val, (int, float)):
                            span_attrs.append({"key": key, "value": {"doubleValue": float(val)}})
                    return


def get_from_attrs(attrs, key):
    if attrs is None or (isinstance(attrs, float) and pd.isna(attrs)):
        return None

    # Case 1: simple dict: {"input.value": "...", ...}
    if isinstance(attrs, dict):
        return attrs.get(key)

    if isinstance(attrs, list):
        for item in attrs:
            if isinstance(item, dict):
                if item.get("key") == key:
                    val = item.get("value")
                    if isinstance(val, dict) and "stringValue" in val:
                        return val["stringValue"]
                    return val
            elif isinstance(item, tuple) and len(item) >= 2:
                if item[0] == key:
                    return item[1]

    return None


def dbnl_df_from_otel_file(path):
    """Load an OTLP JSONL file.

    Returns:
        raw_series: pd.Series of raw OTLP JSON dicts (one per trace)
        flat_df: DataFrame with timestamp, input, output, spans, trace_id
    """
    with open(path, "r") as f:
        raw_series = pd.Series([json.loads(line) for line in f])

    flat_df = dbnl.flatten_otlp_traces_data(raw_series)

    dbnl_spans = dbnl.convert_otlp_traces_data(raw_series)
    flat_df["trace_id"] = [spans[0]["trace_id"] for spans in dbnl_spans]

    return raw_series, flat_df
