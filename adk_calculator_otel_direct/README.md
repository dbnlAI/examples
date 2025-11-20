# Google ADK Calculator DBNL Semantic Convention Extractor

This example shows how to instrument a simple calculator agent using the [Google ADK](https://google.github.io/adk-docs/) to send OTEL traces directly to your DBNL deployment  using the built in trace collector.

```python
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from openinference.instrumentation.google_adk import GoogleADKInstrumentor

tracer_provider = trace_sdk.TracerProvider()
trace_api.set_tracer_provider(tracer_provider)
tracer_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint="http://localhost:8080/otel/v1/traces", # <DBNL_API_URL>/otel/v1/traces
            headers={
                "Authorization": "Bearer <DBNL_API_KEY>", # Find at <DBNL_APP_URL>/tokens, sandbox default: http://localhost:8080/tokens
                "x-dbnl-project-id": "<PROJECT_ID>", # Find at /settings/data-source in your project, see streaming traces in /status page of project
            },
        )
    )
)

GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
```

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

## Create a project and instrument `agents.py`

1. Click on "+ New Project"
2. Fill out a name and description
3. Select or create a Model Connection
4. Select "Trace Ingestion" as your Data Source
5. Copy the code into `agents.py`, you can access the project id later from /settings/data-source of the project
6. Copy your `<DBNL_API_KEY>` from [http://localhost:8080/tokens](http://localhost:8080/tokens)

## Generate example data

```bash
export GEMINI_API_KEY=<YOUR_KEY_HERE>
python3 simulate_usage.py --max-traces 5
```
You can find these traces in the /status page of the project. The [DBNL Data Pipeline](https://docs.dbnl.com/configuration/data-pipeline) will collect and reduce these traces nightly at UTC midnight, after which they will appear in the logs. After 8 days of data have been observed [Insights](https://docs.dbnl.com/workflow/insights) will begin to appear.