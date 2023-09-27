py_deploy(
    name="docker-example",
    entry_point="docker_example.app",
    docker={"compose_chart": True},
    helm={},
    env_export=dict(exclude_globs=["EXCLUDED_*"]),
    healthcheck={
        "port": 8000,
        "path": "/health",
        "probes": "liveness,readiness,startup",
    },
    explicit_ports=[(8001, "/", "http")],
    secret_env_vars={
        "secret1": "secret1_env_var1,secret1_env_var2",
        "secret2": "secret2_env_var3",
    },
)
