# `dbnl` Examples

This repository contains example Jupyter notebooks demonstrating specific `dbnl` usage. Each example is organized in its own folder with its own dependencies and requirements. In most cases, the examples will exist in our [documentation](https://docs.dbnl.com).

## Quick Start

1. Install `uv` (required for package management):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Navigate to an example folder:
   ```bash
   cd quick-start  # or any other example folder
   ```

3. Set up your environment:
   ```bash
   # Create and activate virtual environment
   uv venv --python 3.12 .venv # or any supported python version
   source .venv/bin/activate

   # Install dependencies
   uv pip install -r requirements.txt
   ```

4. Configure environment variables:
   - Copy `env.template` to `.env` in the example folder
   - Or create a `.env` file in the repository root
   - See [Environment Variables Guide](TODO) for more details

5. Run the example:
   - Interactive mode:
     ```bash
     jupyter notebook main.ipynb
     ```
   - Non-interactive mode:
     ```bash
     jupyter nbconvert --to notebook --execute main.ipynb --stdout > /dev/null
     ```

## Adding New Examples

1. Create a new folder with your example name
2. Add your notebooks and `requirements.txt`
3. Create a new workflow file in `.github/workflows/` following the pattern in `run-quick-start.yml`
4. Set up notebook formats:
   ```bash
   jupytext --set-formats ipynb,md your-notebook.ipynb
   ```

## Pre-commit Hooks

This repository uses pre-commit hooks to ensure code quality and maintain notebook synchronization. The hooks will:
- Fix mixed line endings
- Remove trailing whitespace
- Check YAML syntax
- Check for large files being added

To install the hooks:
```bash
pre-commit install
```

## Contributing

1. Fork the repository
2. Create a new branch for your example
3. Add your notebooks and requirements
4. Create a new workflow file
5. Submit a pull request

## License

For Distributional's full documentation, visit [docs.dbnl.com](https://docs.dbnl.com).

## Repository Dependencies

To contribute to this repository, you'll need to install the following dependencies from the root of this repository:
```bash
uv pip install -r requirements.txt
```
