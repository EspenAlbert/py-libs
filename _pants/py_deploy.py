# inspired by
# https://pantsbuild.slack.com/archives/C046T6T9U/p1668559231617069?thread_ts=1668559186.539269&cid=C046T6T9U

PYTHON_MAJOR_MINOR = "3.10"
ARM_IMAGE = "python:3.10.11-slim-bullseye@sha256:2b7d288b3cd5a884c8764aa39488cd39373e25fc9c7218b3f74e2bd623de9ffe"
AMD_IMAGE = "python:3.10.11-slim-bullseye@sha256:364bb889cb48b1e0d66b8aa73b1e952f1d072864205f8abc667f0a15d84de040"

"""
Healthcheck options:
https://docs.docker.com/engine/reference/builder/#healthcheck
--interval=DURATION (default: 30s)
--timeout=DURATION (default: 30s)
--start-period=DURATION (default: 0s)
--start-interval=DURATION (default: 5s)
--retries=N (default: 3)

"""
default_healthcheck_options = (
    ("interval", "30s"),
    ("timeout", "30s"),
    ("start-period", "0s"),
    ("start-interval", "5s"),
    ("retries", "3"),
)


def as_healthcheck_command(healthcheck: dict) -> str:
    """only healthchecks with port and path are supported now"""
    cmd = healthcheck.get("cmd", healthcheck.get("CMD"))
    port = healthcheck.get("port")
    path = healthcheck.get("path", "/")
    py_module: str = healthcheck.get("py_module")  # type: ignore
    unknown_message = (
        f"unknown healthcheck, specify cmd/CMD/port/py_module: {healthcheck}"
    )
    assert cmd or port or py_module, unknown_message
    if not cmd:
        if port:
            cmd = f"curl -f http://localhost:{port}/{path} || exit 1"
        elif py_module:
            script_path = py_module.replace(".", "/")
            healthcheck["python_major_minor"] = PYTHON_MAJOR_MINOR
            cmd = f"/bin/app/lib/python{PYTHON_MAJOR_MINOR}/site-packages/{script_path}.py"
    options = " ".join(
        f"--{name}={healthcheck.get(name, default)}"
        for name, default in default_healthcheck_options
    )
    return f"HEALTHCHECK {options} \\\n  CMD {cmd}"


def dockerfile_pex_instructions(
    is_arm: bool,
    pex_requirements_path: str,
    pex_sources_path: str,
    healthcheck: dict,
    apt_packages: list[str],
) -> list[str]:
    health_command = ""
    apt_install = ""
    apt_copy: list[str] = []
    if healthcheck:
        health_command = as_healthcheck_command(healthcheck)
        if "curl" not in apt_packages:
            apt_packages.append("curl")
    if apt_packages:
        apt = " ".join(apt_packages)
        apt_install = f"RUN apt-get -y update; apt-get -y install {apt}"
        apt_copy.extend(
            f"COPY --from=deps /usr/bin/{p} /usr/bin/{p}" for p in apt_packages
        )
        lib_dir = "aarch64-linux-gnu" if is_arm else "x86_64-linux-gnu"
        apt_copy.append(f"COPY --from=deps /usr/lib/{lib_dir} /usr/lib/{lib_dir}")
    base_image = ARM_IMAGE if is_arm else AMD_IMAGE
    lines = [
        "# syntax=docker/dockerfile:1.6.0",
        f"FROM {base_image} as deps",
        apt_install,
        f"COPY {pex_requirements_path} /binary.pex",
        "RUN PEX_TOOLS=1 PEX_VERBOSE=2 python /binary.pex venv --scope=deps --compile /bin/app",
        f"FROM {base_image} as srcs",
        f"COPY {pex_sources_path} /binary.pex",
        "RUN PEX_TOOLS=1 PEX_VERBOSE=2 python /binary.pex venv --scope=srcs --compile /bin/app",
        f"FROM {base_image}",
        'ENTRYPOINT ["/bin/app/pex"]',
        *apt_copy,
        "COPY --from=deps /bin/app /bin/app",
        "COPY --from=srcs /bin/app /bin/app",
        health_command,
    ]
    return [l for l in lines if l]


def py_deploy(
    *,
    name: str,
    entry_point: str,
    docker: dict = None,
    helm: dict = None,
    env_arm: str = "linux_arm",
    env_amd: str = "linux_amd",
    resolve: str = "python-default",
    env_export: dict = None,
    healthcheck: dict = None,
    explicit_ports: list[dict] = None,
    apt_packages: list[str] = None,
):
    apt_packages = apt_packages or []
    explicit_ports = explicit_ports or []
    assert all(
        len(port) == 3 for port in explicit_ports
    ), "ports are tuple with (number, path, port_protocol{http|grpc|grpc-web|tcp|tls|udp|http2}"
    healthcheck = healthcheck or {}
    # pants require str->str dictionary
    healthcheck = {key: str(value) for key, value in healthcheck.items()}
    use_docker = docker is not None
    use_helm = helm is not None
    parent = build_file_dir()
    parent_path = str(parent).replace("/", ".")
    dir_name = parent.name
    BUILD_NUMBER = env("BUILD_NUMBER", "latest")

    python_sources(name=dir_name)

    for cpu in ["arm", "amd"]:
        is_arm = cpu == "arm"
        pex_filestem = f"{name}-{cpu}"
        pex_filename = f"{name}-{cpu}.pex"
        pex_deps_filestem = f"{pex_filestem}-deps"
        pex_deps_filename = f"{pex_deps_filestem}.pex"
        pex_binary_kwargs = dict(
            name=pex_filestem,
            dependencies=[f":{dir_name}"],
            entry_point=entry_point,
            environment=env_arm if is_arm else env_amd,
            tags=[cpu],
            include_tools=True,
            layout="packed",
            execution_mode="venv",
            resolve=resolve,
        )
        pex_binary(
            **dict(
                pex_binary_kwargs,
                name=pex_deps_filestem,
                include_sources=False,
                include_requirements=True,
            )
        )
        pex_binary(
            **dict(
                pex_binary_kwargs,
                name=pex_filestem,
                include_sources=True,
                include_requirements=False,
            )
        )
        if use_docker:
            docker_image(
                name=f"{name}-{cpu}-docker",
                tags=[cpu],
                image_tags=[f"{BUILD_NUMBER}-{cpu}"],
                dependencies=[],
                repository=name,
                instructions=dockerfile_pex_instructions(
                    is_arm=is_arm,
                    pex_requirements_path=f"{parent_path}/{pex_deps_filename}",
                    pex_sources_path=f"{parent_path}/{pex_filename}",
                    healthcheck=healthcheck,
                    apt_packages=apt_packages,
                ),
                source=None,
                compose_enabled=True,
                compose_chart="chart"
                if docker.get("compose_chart", False) and not is_arm
                else "",
                compose_chart_name=name,
                compose_env_export=env_export or {},
                app_healthcheck=healthcheck,
                app_ports=explicit_ports,
            )
    if use_helm:
        chart_path = "chart"
        chart_resource_name = f"chart_resources_{name}"
        resources(
            name=chart_resource_name,
            sources=[f"{chart_path}/*", f"{chart_path}/templates/*"],
        )
        helm_chart(
            name=f"{name}-chart",
            chart=f"{chart_path}/Chart.yaml",
            sources=[f"{chart_path}/Chart.yaml"],
            dependencies=[f":{chart_resource_name}"],
            tags=["chart"],
        )
