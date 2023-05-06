py_deploy(
    name="docker-example",
    entry_point="docker_example.app",
    docker={"compose_chart": True},
    helm={},
    env_export=dict(exclude_globs=["EXCLUDED_*"]),
)
