# inspired by
# https://pantsbuild.slack.com/archives/C046T6T9U/p1668559231617069?thread_ts=1668559186.539269&cid=C046T6T9U



def dockerfile_pex_instructions(
    version: str, is_arm: bool, pex_requirements_path: str, pex_sources_path: str
) -> list[str]:
    BASE_IMAGES_ARM_AMD = {
        "3.10.11": (
            "python:3.10.11-slim-bullseye@sha256:2b7d288b3cd5a884c8764aa39488cd39373e25fc9c7218b3f74e2bd623de9ffe",
            "python:3.10.11-slim-bullseye@sha256:364bb889cb48b1e0d66b8aa73b1e952f1d072864205f8abc667f0a15d84de040",
        )
    }
    arm_image, amd_image = BASE_IMAGES_ARM_AMD[version]
    base_image = arm_image if is_arm else amd_image
    return [
        f"FROM {base_image} as deps",
        f"COPY {pex_requirements_path} /binary.pex",
        "RUN PEX_TOOLS=1 PEX_VERBOSE=2 python /binary.pex venv --scope=deps --compile /bin/app",
        f"FROM {base_image} as srcs",
        f"COPY {pex_sources_path} /binary.pex",
        "RUN PEX_TOOLS=1 PEX_VERBOSE=2 python /binary.pex venv --scope=srcs --compile /bin/app",
        f"FROM {base_image}",
        'ENTRYPOINT ["/bin/app/pex"]',
        "COPY --from=deps /bin/app /bin/app",
        "COPY --from=srcs /bin/app /bin/app",
    ]


def py_deploy(
    *,
    name: str,
    entry_point: str,
    docker: dict = None,
    helm: dict = None,
    version: str = "3.10.11",
    env_arm: str = "linux_arm",
    env_amd: str = "linux_amd",
    resolve: str = "python-default",
    env_export: dict=None
):
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
            resolve=resolve
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
                    version=version,
                    is_arm=is_arm,
                    pex_requirements_path=f"{parent_path}/{pex_deps_filename}",
                    pex_sources_path=f"{parent_path}/{pex_filename}",
                ),
                source=None,
                compose_enabled=True,
                compose_chart="chart" if docker.get("compose_chart", False) and not is_arm else "",
                compose_chart_name=name,
                compose_env_export=env_export or {}
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
