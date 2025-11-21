# Deploy a Local Sandbox with Example Data

This guide walks you through using the DBNL Sandbox and SDK Log Ingestion using the Python SDK to create your first project, submit log data to it, and start analyzing.

See a 3 min walkthrough in our [overview video](https://www.youtube.com/watch?v=DfL-FcB5W6Q).

## Get and install the latest DBNL SDK and Sandbox.

```bash
pip install --upgrade dbnl
dbnl sandbox start
dbnl sandbox logs # See spinup progress
```

Log into the sandbox at [http://localhost:8080](http://localhost:8080) using

* Username: `admin`
* Password: `password`

## Create a Model Connection

Every DBNL Project requires a [Model Connection](https://docs.dbnl.com/configuration/model-connections) to create LLM-as-judge metrics and perform analysis.

1. Click on the "Model Connections" tab on the left panel of [http://localhost:8080](http://localhost:8080)
2. Click "+ Add Model Connection"
3. [Create a Model Connection](https://docs.dbnl.com/configuration/model-connections#creating-a-model-connection) with the name: `quickstart_model`

## Create a project and upload example data using the SDK

```bash
pip install notebook # if you don't already have jupyter
jupyter notebook DBNL-quickstart.ipynb
```

After uploading, the data pipeline will run automatically. Depending on the latency of your [Model Connection](https://docs.dbnl.com/configuration/model-connections), it may take several minutes to complete all steps (Ingest → Enrich → Analyze → Publish). Check the Status page to monitor progress.

## Discover, investigate, and track behavioral signals

After the data processing completes (check the Status page):

1. Go back to the DBNL project at [http://localhost:8080](http://localhost:8080)
2. Discover your first behavioral signals by clicking on "Insights"
3. Investigate these insights by clicking on the "Explorer" or "Logs" button
4. Track interesting patterns by clicking "Add Segment to Dashboard"

**No Insights appearing?** The system needs at least 7 days of data to establish behavioral baselines. If you just uploaded data, check the Status page to ensure all pipeline steps (Ingest → Enrich → Analyze → Publish) completed successfully.

## Next Steps

* Dive deeper into the documentation at https://docs.dbnl.com
* Need help? Contact [support@distributional.com](mailto:support@distributional.com) or visit [distributional.com/contact](https://distributional.com/contact)