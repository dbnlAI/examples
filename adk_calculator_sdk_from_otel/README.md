# Google ADK Calculator DBNL Semantic Convention Extractor

This example shows how to instrument the collection of data required by the [DBNL Semantic Convention](https://docs.dbnl.com/configuration/dbnl-semantic-convention) automatically from a simple calculator agent using the [Google ADK](https://google.github.io/adk-docs/) through a local OTEL collector writing raw spans to file in the [Open Inference](https://github.com/Arize-ai/openinference) semantic convention, which can then be easily augmented and uploaded to DBNL via the Python SDK. DBNL will automatically flatten traces in this format contained in the `traces_data` column in a pandas dataframe upon upload.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from openinference.instrumentation.google_adk import GoogleADKInstrumentor

provider = TracerProvider()
trace.set_tracer_provider(provider)

exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318/v1/traces",  # matches your otelcol http receiver
)

processor = BatchSpanProcessor(exporter)
provider.add_span_processor(processor)

GoogleADKInstrumentor().instrument(tracer_provider=provider)
```

We will also show how you can load this data into a dataframe and augment it with extra information like user feedback, expected outputs, or any other data related to the traces that will help with analysis.

## Setup

First, install the requirements and spin up your local sandbox.

```bash
pip install -r requirements.txt
dbnl sandbox start
dbnl sandbox logs # See spinup progress
```

Log into the sandbox at [http://localhost:8080](http://localhost:8080) using

* Username: `admin`
* Password: `password`

## Generate example data

```bash
export GEMINI_API_KEY=<YOUR_KEY_HERE>
otelcol --config otel-collector-config.yaml
python3 simulate_usage.py --max-traces 500 # This will take about an hour
```

Or, grab data from 500 traces already computed.

```bash
cp data/traces.jsonl .
```

Each line of the `traces.jsonl` file contains a JSON string in OTEL format using the [Open Inference](https://github.com/Arize-ai/openinference) semantic convention.

## Load the trace data and send it to DBNL via the Python SDK

When your traces data is formatted like this we can put it in the `traces_data` column of a pandas dataframe and DBNL will convert it into the DBNL Semantic Convention for us. All we need to do is pull out the required `input`, `output`, and `timestamp` fields, which is done in the helper functions.

```python
from dbnl_otel_converter import dbnl_df_from_otel_file

df = dbnl_df_from_otel_file("traces.jsonl")

data_start_t = df['timestamp'].min().replace(hour=0, minute=0, second=0, microsecond=0)
data_end_t = data_start_t + timedelta(days=1)

dbnl.log(
    project_id=project.id,
    data_start_time=data_start_t,
    data_end_time=data_end_t,
    data=df,
)
```

For the full example run the notebook

```bash
notebook otel_data_load_only.ipynb
```

## Load and augment the trace data and send it to DBNL via the Python SDK

Once the data is loaded into a pandas dataframe we can also augment it with more data like total cost, user feedback, expected outputs, or session information like whether the agent completed the task or the user took an action. Any extra columns added to the dataframe will be added to the logs as top level fields during via the [DBNL Data Pipeline](https://docs.dbnl.com/configuration/data-pipeline) process.

In this example notebook we will show adding
- An estimated `total_cost` (part of the DBNL Semantic Convention)

```bash
notebook otel_data_load_and_augment.ipynb
```