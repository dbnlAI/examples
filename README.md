# `dbnl` Examples

This repository contains example Jupyter notebooks demonstrating specific `dbnl` usage. Each example is organized in its own folder with its own dependencies and requirements. In most cases, the examples will exist in our [documentation](https://docs.dbnl.com).

## Quick Start

1. Navigate to an example folder:
   ```sh
   cd quickstart  # or any other example folder
   ```

2. Install Dependencies
   ```sh
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `env.template` to `.env` in the example folder
   - Or create a `.env` file in the repository root
   - See [Environment Variables Guide](https://docs.dbnl.com/install-sdk#environment-variables) for more details

5. Run the example:
   - Interactive mode:
     ```sh
     jupyter notebook main.ipynb
     ```
   - Non-interactive mode:
     ```sh
     jupyter execute main.ipynb
     ```

## Adding New Examples

1. Create a new folder with your example name
2. Add your notebooks and `requirements.txt`
3. Update the GitHub Workflows to include your new Jupyter Notebook
4. Set up notebook formats:
   ```bash
   jupytext --set-formats ipynb,md your-notebook.ipynb
   ```
