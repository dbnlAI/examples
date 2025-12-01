# DBNL Data Ingestion Example - Manually Constructing JSON Spans

This example shows how you can instrument a Google ADK agent to extract all of the information needed for the complete DBNL Semantic Convention and put it into a local `jsonl` file in just a few lines of code.

Note: This path is _not recommended_ unless you have a mature ETL pipeline, but not OTEL, which requires you to manually join data to create spans.

```python
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from dbnl_semconv_file_exporter import DBNLSemConvFileExporter

tracer_provider = TracerProvider()
trace_api.set_tracer_provider(tracer_provider)
tracer_provider.add_span_processor(
    BatchSpanProcessor(DBNLSemConvFileExporter('./traces.jsonl'))
)
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
python3 simulate_usage.py --max-traces 5
```

Or, grab data from 1000 traces already computed.

```bash
cp data/traces.jsonl .
```

Each line of the `traces.jsonl` file contains a JSON string that includes nearly all of the [DBNL Semantic Convention](https://docs.dbnl.com/configuration/dbnl-semantic-convention). By giving DBNL the richest possible information about your agent like this it can provide the most detailed analysis and insights.

## Load the trace data and send it to DBNL via the Python SDK

When your traces data is formatted like this we only need to apply a quick transformation on the timestamps and then it is ready to send to DBNL.

```python
# Load the JSONL file
df = pd.read_json('traces.jsonl', lines=True)

# Convert timestamp columns to datetime
df['timestamp'] = pd.to_datetime(df['timestamp'])

# For nested timestamps in spans, we also need to convert to datetime
def convert_span_times(spans):
    for span in spans:
        span['start_time'] = pd.to_datetime(span['start_time'])
        span['end_time'] = pd.to_datetime(span['end_time'])
    return spans

df['spans'] = df['spans'].apply(convert_span_times)

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
notebook adk_calc_data_load_only.ipynb
```

## Load and augment the trace data and send it to DBNL via the Python SDK

Once the data is loaded into a pandas dataframe we can also augment it with more data like user feedback, expected outputs, or session information like whether the agent completed the task or the user took an action. Any extra columns added to the dataframe will be added to the logs as top level fields during via the [DBNL Data Pipeline](https://docs.dbnl.com/configuration/data-pipeline) process.

In this example notebook we will show adding
- A simulated `feedback_score` (part of the DBNL Semantic Convention)
- A simulated `feedback_text` (part of the DBNL Semantic Convention)
- A calculated `output_expected` (custom field)

```bash
notebook adk_calc_data_load_and_augment.ipynb
```