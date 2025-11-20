# Langfuse to DBNL Converter

This script converts Langfuse trace and observation export files into the DBNL format, which adheres to the [DBNL semantic convention](https://docs.dbnl.com/configuration/dbnl-semantic-convention).

## Overview

The script takes two Langfuse export files as input:
- `lf-traces-export.jsonl` - Contains high-level trace information
- `lf-observations-export.jsonl` - Contains detailed span/observation data

Get these files by going to your langfuse project and clicking the export button on the /traces and /observations pages. Make sure you have all columns you want exported selected.

And produces:
- `traces.jsonl` - DBNL-formatted traces ready for pandas DataFrame loading and upload to DBNL

## Usage

### Basic Usage

```bash
python langfuse_to_dbnl.py \
  --traces data/lf-traces-export.jsonl \
  --observations data/lf-observations-export.jsonl \
  --output traces.jsonl
```

### Command-Line Options

- `--traces` - Path to Langfuse traces export file (default: `lf-traces-export.jsonl`)
- `--observations` - Path to Langfuse observations export file (default: `lf-observations-export.jsonl`)
- `--output` - Path to output DBNL traces file (default: `traces.jsonl`)

## Loading into Pandas

After conversion, you can load the data into a pandas DataFrame, augment it with extra fields, and upload it to DBNL. See the example notebook for more details.

```bash
notebook load_and_augment_langfuse_traces.ipynb
```
