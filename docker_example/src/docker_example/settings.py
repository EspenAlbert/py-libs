from model_lib import port_info
from pydantic import BaseSettings


class DockerExampleSettings(BaseSettings):  # type: ignore
    name: str
    env: str = "default"
    EXCLUDED_FROM_ENV_VARS: bool = True
    PORT: int = port_info(8000, url_prefix="/", protocol="http")
