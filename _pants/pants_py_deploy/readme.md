# Pants py_deploy plugin
- Purpose: Make it easy to maintain docker-compose files and helm-charts across projects
- Goals
  - Support updating services.{service_name}.
    - `environment` by scanning source code
    - `ports` by scanning source code
  - Support updating {chart}/
    - `values.yaml`
    - `{deployment|statefulset}.yaml`
  - Use [Pantsbuild pants](https://www.pantsbuild.org/docs) to write a plugin that can be pip installed
  - Then invoking it should be `pants fix ::`
  - Less pants boilerplate and support multi-platform (arm+amd) with a macro
  - Enabling docker-compose|helm-chart templates by using the macro and adding fields to pex_binary

## Draft api
- `BUILD` file
```python
py_deploy(
    name="app-name",
    entrypoint=package_name,
    docker={},
    helm={},# support more config in the future
)
```
- generates
  - 4 `pex_binary` targets
    - Each platform has one `pex_binary` for sources and one `pex_binary` for requirements
  - 2 `docker_image` targets
    - Both pex_binaries are copied, copies requirements 1st to take advantage of docker build cache
  - 1 `helm_chart` with a `resource` of all the files u
- Usage in `pants publish ::`
  - docker and helm repository = `app-name`
  - tags:, `app-name-amd`, `app-name-arm`, `app-name-chart`
- Usage in `pants fix ::`
  - `docker-compose.yaml` file & `chart/*` are create if they don't exist
  - if they exist: ensure environment & ports are up-to-date

## Later ideas
- support passing `env_config=dict(ignore_globs=[], include_globs=[])`
- support analyzing env-vars and using them for adding services like postgres/rabbitmq/mongo etc. to the docker-compose file
