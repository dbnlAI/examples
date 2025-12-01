# Hyperparameter Optimization with NeMo Agent Toolkit and DBNL

This example demonstrates using NVIDIA's NeMo Agent Toolkit (NAT) and DBNL to perform behavioral analytics to discover issues in production.

![AB_test_gif](https://content.gitbook.com/content/exM6vU0DHdLH7TyRgvH9/blobs/4ElwsGRSwpnrX1ACLmXj/hpo_demo_small_opt.gif)

This example follows the following path:
1. Start with a simple calculator agent, which is similar to our Google ADK calculator agents from the other examples, but wrapped in NAT.
2. Observe that the calculator performs well offline with the default `configs/config_v0.yaml` with respect to a simple dataset `data/eval_dataset_small_numbers_only.json` that we think is representative of production data _before_ we actually deploy to production.
3. Simulate production usage and upload the data to DBNL
4. Observe issues with the agent related to data outside of our initial eval dataset. Use DBNL to augment our eval dataset to be more representative of real production data.
5. Perform Hyperparmeter Optimization (HPO) using NAT HPO on the agent to find a better value for the hyperparameter given this new DBNL enhanced dataset, resulting in `configs/config_v1.yaml`. Observe this new value does well offline.
6. Simulate production usage with the new config, uploading data to DBNL.
7. Observe that the original issue has been resolved.

This represents a complete cycle of the [Adaptive Analytics Flywheel](https://docs.dbnl.com/#adaptive-analytics-flywheel).

Note: For the purposes of this example, the parameter being tuned is intentionally an error term with a known "best" value. In a real production setting the same concepts will apply, this example was chosen for ease of understanding and ability to reproduce quickly and cheaply.

## Setup DBNL Sandbox

```bash
pip install -e .
dbnl sandbox start
dbnl sandbox logs # See spinup progress
```

Log into the sandbox at [http://localhost:8080](http://localhost:8080) using

* Username: `admin`
* Password: `password`

Create a [Model Connection](https://docs.dbnl.com/configuration/model-connections) named `quickstart_model`.

Set your Gemini API key:

```bash
export GEMINI_API_KEY=<YOUR_KEY_HERE>
```

## Step 1: Evaluate on Initial Dataset (small numbers only)

```bash
nat eval --config_file configs/eval_config_v0_small_only.yaml
```

Results show low error on small numbers (0-40):
```
"average_score": 6.94999613415348e-13
```

The agent appears to work correctly!


## Step 2: Deploy to Production

Start the OTEL collector and generate production traces:

```bash
otelcol --config otel-collector-config.yaml &
python scripts/run_batch.py --config_file configs/config_v0.yaml --input_file data/prod_data_v0_8days.json
mv traces.jsonl traces_v0.jsonl
```

Or grab precomputed traces:
```bash
curl -o traces_v0.jsonl https://dbnl-demo-public.s3.us-east-1.amazonaws.com/nemo_agent_toolkit_hpo_example/traces_v0.jsonl
```

Upload to DBNL via the notebook:
```bash
jupyter notebook dbnl_upload.ipynb
```

## Step 3: Discover Issues in DBNL

In the DBNL platform, you'll notice errors appearing for calculations involving larger numbers. The `absolute_error` metric shows significant deviation from expected values when operands sum to values approaching 100. The [Insights](https://docs.dbnl.com/workflow/insights) will also catch this in a completely unsupervised manner.

## Step 4: Evaluate on More Complete Dataset Given DBNL Insights

```bash
nat eval --config_file configs/eval_config_v0_full.yaml
```

Results reveal the problem on full range (0-100):
```
"average_score": 0.4120745455871681
```

The error is much higher with data that DBNL found to be more representative!

## Step 5: Run Hyperparameter Optimization

```bash
nat optimize --config_file configs/optimize_config.yaml
```

NAT uses Optuna to search for the optimal `hyper_error_term` in the range [-1.0, 1.0] using a Tree Parzen Estimator method, finding that `hyper_error_term = 0.0032446634095984403` minimizes error.

If we allowed it to run for more iterations or used a different optimization method it would find `0.0` eventually.

## Step 6: Verify the Fix

```bash
nat eval --config_file configs/eval_config_v1_full.yaml
```

Results with optimized parameters:
```
"average_score": 0.001337043200092669
```

If we set `hyper_error_term = 0` we can reduce the error to exactly 0.

## Step 7: Deploy Fixed Version and Verify in DBNL

```bash
pkill -SIGTERM otelcol && otelcol --config otel-collector-config.yaml &
python scripts/run_batch.py --config_file configs/config_v1.yaml --input_file data/prod_data_v1_8days.json
mv traces.jsonl traces_v1.jsonl
```

Or grab precomputed traces:
```bash
curl -o traces_v1.jsonl https://dbnl-demo-public.s3.us-east-1.amazonaws.com/nemo_agent_toolkit_hpo_example/traces_v1.jsonl
```

Upload the new data via the notebook and observe in DBNL that errors have been resolved.

```bash
jupyter notebook dbnl_upload.ipynb
```
