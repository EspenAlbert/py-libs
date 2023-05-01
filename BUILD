docker_environment(
    name="python_bullseye_amd",
    platform="linux_x86_64",
    image="python:3.10.11-slim-bullseye@sha256:364bb889cb48b1e0d66b8aa73b1e952f1d072864205f8abc667f0a15d84de040",
)

docker_environment(
    name="python_bullseye_arm",
    platform="linux_arm64",
    image="python:3.10.11-slim-bullseye@sha256:2b7d288b3cd5a884c8764aa39488cd39373e25fc9c7218b3f74e2bd623de9ffe",
)

local_environment(
    name="linux_amd",
    compatible_platforms=["linux_x86_64"],
    fallback_environment="python_bullseye_amd",
)

local_environment(
    name="linux_arm",
    compatible_platforms=["linux_arm64"],
    fallback_environment="python_bullseye_arm",
)
