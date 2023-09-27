from pydantic import BaseSettings

from model_lib import port_info


class DockerExampleSettings(BaseSettings):  # type: ignore
    name: str
    env: str = "default"
    EXCLUDED_FROM_ENV_VARS: bool = True
    secret1_env_var1: str = "DEFAULT1"
    secret1_env_var2: str = "DEFAULT2"
    secret2_env_var3: str = "DEFAULT3"
    PORT: int = port_info(8000, url_prefix="/", protocol="http")
