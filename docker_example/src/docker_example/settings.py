from pydantic import BaseSettings

from model_lib import port_info


class DockerExampleSettings(BaseSettings):
    name: str
    env: str = "default"
    PORT: int = port_info(8000, url_prefix="/", protocol="http")
