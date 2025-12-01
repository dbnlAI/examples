# Google ADK Calculator A/B Test Example

This example shows how to run an A/B test driven by behavioral analytics.

![AB_gif](https://docs.dbnl.com/~gitbook/image?url=https%3A%2F%2Fcontent.gitbook.com%2Fcontent%2FexM6vU0DHdLH7TyRgvH9%2Fblobs%2FysbW5rcjQhNYYsl5QNmz%2Fab_demo_small_opt.gif&width=768&dpr=2&quality=100&sign=fa026fbf&sv=2)

First, we instrument the collection of data required by the [DBNL Semantic Convention](https://docs.dbnl.com/configuration/dbnl-semantic-convention) automatically from a simple calculator agent using the [Google ADK](https://google.github.io/adk-docs/) through a local OTEL collector writing raw spans to file in the [Open Inference](https://github.com/Arize-ai/openinference) semantic convention, which can then be easily augmented and uploaded to DBNL via the Python SDK.

Then we observe an issue with our agent through via the Insights provided by DBNL. We triage this issue through exporation and investigation on the DBNL platform, finding the issue.

We then run a simulated A/B test of our resolution and observe the results and analytics on the DBNL platform, ultimately correcting the issue.

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

## Generate inital example data

```bash
export GEMINI_API_KEY=<YOUR_KEY_HERE>
otelcol --config otel-collector-config.yaml &
python3 simulate_usage.py --max-traces 800 # Simulating ~8 days of data at ~100 traces/day
mv traces.jsonl data/traces_v0_only.jsonl
```

Or, grab some precomputed traces from the example S3 bucket.

```bash
curl -o data/traces_v0_only.jsonl https://dbnl-demo-public.s3.us-east-1.amazonaws.com/ab_test_example/traces_v0_only.jsonl
```

Each line of the `traces.jsonl` file contains a JSON string in OTEL format using the [Open Inference](https://github.com/Arize-ai/openinference) semantic convention.

## Load the and augment trace data and send it to DBNL via the Python SDK

Following a similar path to the [adk_calculator_sdk_from_otel](adk_calculator_sdk_from_otel/README.md) example we can augment the data with useful additional information and load it into DBNL.

```bash
notebook otel_data_load_and_augment.ipynb
```

After loading this first batch of data we can explore the project and discover the bug through the [Adaptive Analytics Workflow](https://docs.dbnl.com/workflow/adaptive-analytics-workflow) (Hint: the addition tool multiplies the two inputs instead of taking the sum)

## Generate the A/B testing example data

```bash
pkill -SIGTERM otelcol && otelcol --config otel-collector-config.yaml & # We need to restart the collector since we moved the traces.jsonl file
python3 simulate_usage.py --version_split_ratio 0.5 --max-traces 300 # Simulating 3 days of data of 50% v0 vs v1
mv traces.jsonl data/traces_mix.jsonl
pkill -SIGTERM otelcol && otelcol --config otel-collector-config.yaml & # We need to restart the collector since we moved the traces.jsonl file
python3 simulate_usage.py --version_split_ratio 0.0 --max-traces 300 # Simulating 3 days of data of 100% v1
mv traces.jsonl data/traces_v1_only.jsonl
```

or, grab these from the S3 bucket

```bash
curl -o data/traces_mix.jsonl https://dbnl-demo-public.s3.us-east-1.amazonaws.com/ab_test_example/traces_mix.jsonl
curl -o data/traces_v1_only.jsonl https://dbnl-demo-public.s3.us-east-1.amazonaws.com/ab_test_example/traces_v1_only.jsonl
```

Now we can finish uploading this simulated data and observe the multiplication issue has been resolved back in the notebook.

```bash
notebook otel_data_load_and_augment.ipynb
```