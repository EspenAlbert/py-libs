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
test-py310:
  uv run --python 3.10 pytest
test-py311:
  uv run --python 3.11 pytest
test-py312:
  uv run --python 3.12 pytest
test-py313:
  uv run --python 3.13 pytest
cov:
  export RUN_SLOW=false && uv run pytest --cov --cov-report=html
cov-full:
  export RUN_SLOW=true && uv run pytest --cov --cov-report=html
open-cov: cov
  open htmlcov/index.html
open-cov-full: cov-full
  open htmlcov/index.html
pre-release:
  uv venv -p python3.11 .venv-ci
  echo "dist/model_lib-1.0.0+rc1-py3-none-any.whl[toml]" > .venv-ci/requirements.txt
  uv pip sync --python .venv-ci/bin/python .venv-ci/requirements.txt
  uv pip install --python .venv-ci/bin/python -r .venv-ci/requirements.txt
  .venv-ci/bin/python scripts/model_lib_pre_release.py
