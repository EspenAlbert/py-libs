<p align="center">
    <a href="https://github.com/EspenAlbert/py-libs/actions/workflows/ci.yaml" target="_blank">
        <img src="https://github.com/EspenAlbert/py-libs/actions/workflows/ci.yaml/badge.svg">
    </a>
    <a href="https://pypi.org/project/model-lib/" target="_blank">
        <img src="https://img.shields.io/pypi/v/model-lib.svg">
    </a>
    <a href="https://pypi.org/project/model-lib/" target="_blank">
        <img src="https://img.shields.io/pypi/pyversions/model-lib.svg">
    </a>
    <a href="https://codecov.io/gh/EspenAlbert/py-libs" target="_blank">
        <img src="https://img.shields.io/codecov/c/github/EspenAlbert/py-libs?color=%2334D058" alt="Coverage">
    </a>
    <a href="https://github.com/psf/black" target="_blank">
            <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
    </a>
    <a href="https://github.com/EspenAlbert/py-libs/blob/main/LICENSE" target="_blank">
            <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
    </a>
    <a href="https://github.com/pre-commit/pre-commit"><img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit" alt="pre-commit" style="max-width:100%;"></a>

</p>

# py-libs

- An experiment for sharing python packages
- [compose_chart_export](./compose_chart_export/readme.md)
	- `pip install compose-chart-export`
- [docker_compose_parser](./docker_compose_parser/readme.md)
	- `pip install docker-compose-parser`
- [model_lib-pydantic base models with convenient dump methods](./model_lib/readme.md)
	- `pip install model-lib`
- [zero_lib-handy standalone scripts without 3rdparty dependencies](./zero_3rdparty/readme.md)
	- `pip install zero-3rdparty`

## Hierarchy

```mermaid
flowchart TD
    model_lib --> zero_3rdparty
    compose_chart_export --> model_lib
    docker_compose_parser --> model_lib
    compose_chart_export --> docker_compose_parser
    pants_py_deploy --> compose_chart_export
    pants_py_deploy --> docker_compose_parser

    click zero_3rdparty href "/py-libs/zero_3rdparty" "zero_3rdparty docs"
    click model_lib href "/py-libs/model_lib" "model_lib docs"
    click docker_compose_parser href "/py-libs/docker_compose_parser" "docker_compose_parser docs"
    click compose_chart_export href "/py-libs/compose_chart_export" "compose_chart_export docs"
    click pants_py_deploy href "/py-libs/_pants/pants_py_deploy" "pants_py_deploy docs"
```

- (Click) on a library to see the documentation
- The higher up in the hierarchy the more dependencies needs to be installed
	- e.g., `zero_3rdparty` has no dependencies and `pants_py_deploy` depends on all the others

## Local Installation

- [Install pants](https://www.pantsbuild.org/v2.17/docs/installation)
	- `brew install pantsbuild/tap/pants`

```shell
export PANTS_PYTHON_RESOLVES_TO_INTERPRETER_CONSTRAINTS="{'python-default': ['==3.10.*']}" # choose the version of python you like
pants export --export-resolve=python-default
# import the venv to pycharm/vs code, e.g., dist/export/python/virtualenvs/python-default/3.10.12
```
