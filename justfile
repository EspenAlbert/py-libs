build:
  uv build --package zero-3rdparty
  uv build --package model-lib
fix:
  uv run ruff check --fix .
fmt:
  uv run ruff format .
lint:
  uv run ruff check .
type:
  uv run pyright
test:
  uv run pytest
cov:
  uv run pytest --cov --cov-report=html
open-cov: cov
  open htmlcov/index.html
pre-release:
  uv venv -p python3.11 .venv-ci
  echo "dist/model_lib-1.0.0+rc1-py3-none-any.whl[toml]" > .venv-ci/requirements.txt
  uv pip sync --python .venv-ci/bin/python .venv-ci/requirements.txt
  uv pip install --python .venv-ci/bin/python -r .venv-ci/requirements.txt
  .venv-ci/bin/python scripts/model_lib_pre_release.py
