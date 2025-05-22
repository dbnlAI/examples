---
jupyter:
  jupytext:
    formats: ipynb,md
    text_representation:
      extension: .md
      format_name: markdown
      format_version: '1.3'
      jupytext_version: 1.16.7
  kernelspec:
    display_name: .venv
    language: python
    name: python3
---

### Import Modules

```python
from datetime import datetime

import dbnl
import pandas as pd

# meo
```


### Load Sample Datasets

```python
COLUMN_TYPES = {0: str, "happiness_score": "category", "urgency_score": "category"}
dataset_1 = pd.read_csv("data/dataset_1.csv", index_col=0, dtype=COLUMN_TYPES)
dataset_2 = pd.read_csv("data/dataset_2.csv", index_col=0, dtype=COLUMN_TYPES)
```

### Login to `dbnl`

```python
dbnl.login()
```

### Create New Project

```python
now = datetime.now().isoformat()
project = dbnl.get_or_create_project(name=f"quickstart-{now}")
```

### Create Run and Report Results

```python
run = dbnl.report_run_with_results(
    project=project, display_name="Dataset 1 Run", column_data=dataset_1.reset_index()
)
```

### Set Run as Baseline

```python
dbnl.set_run_as_baseline(
    run=run,
)
```

### Create another Run and Start a Test Session

```python
run = dbnl.report_run_with_results_and_start_test_session(
    project=project, display_name="Dataset 2 Run", column_data=dataset_2.reset_index()
)
```

## Verify your project is on the website, which will complete the quickstart.
Click on one of the run urls displayed above to see the created run in `dbnl`

# ![Run Details Page](main_files/image.png)

