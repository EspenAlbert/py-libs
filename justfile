build:
  uv build --package model-lib
  uv build --package zero-3rdparty
lint:
  uv run ruff .
test:
  uv run pytest
cov:
  uv run pytest --cov --cov-report=html
open-cov: cov
  open htmlcov/index.html
