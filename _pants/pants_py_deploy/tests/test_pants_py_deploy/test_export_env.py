from typing import Dict

from compose_chart_export.ports import PrefixPort
from pants_py_deploy.export_env import REQUIRED, read_env_and_ports

prefix_script = """
from pydantic import BaseSettings


class Settings(BaseSettings):
    class Config:
        env_prefix = "utils_"

    domain: str = ""
"""

no_prefix_script = """
from pydantic import BaseSettings


class Settings(BaseSettings):
    name: str = "unknown"
"""

required_env_var_script = """
from pydantic import BaseSettings


class Settings(BaseSettings):
    name: str
"""


def read_env(script) -> Dict[str, str]:
    return read_env_and_ports(script)[0]


def test_read_env_no_prefix():
    assert read_env(no_prefix_script) == {"name": "unknown"}


def test_read_env_with_prefix():
    assert read_env(prefix_script) == {"utils_domain": ""}


def test_read_env_required():
    assert read_env(required_env_var_script) == {"name": "__REQUIRED__"}


with_env_field = """
class BridgeSettings(BaseEnvVars):
    class Config:
        env_prefix = "bridge_"

    ros_master_uri: str = Field("http://master:11311", env="ROS_MASTER_URI")

"""


def test_read_env_from_field():
    assert read_env(with_env_field) == {"ROS_MASTER_URI": "http://master:11311"}


with_docker_default = """
class BridgeSettings(BaseEnvVars):
    ros_initial_publish_delay: float = docker_or_cls_def_default(
        docker_default=0.4, cls_default=0
    )
"""


def test_read_docker_default():
    assert read_env(with_docker_default) == {"ros_initial_publish_delay": "0.4"}


direct_default_value = """
import logging
class RabbitmqSettings(BaseEnvVars):
    class Config:
        env_prefix = "rabbitmq_"
    log_level_pika: int = logging.WARNING
"""


def test_read_direct_default_value():
    assert read_env(direct_default_value) == {"rabbitmq_log_level_pika": "30"}


random_string_vars = """
class AwsSettings(BaseEnvVars):
    class Config:
        env_prefix = "aws_"

    access_key_id: str = Field(default=RANDOM_STRING, env="AWS_ACCESS_KEY_ID")
    secret_access_key: str = Field(default=RANDOM_STRING, env="AWS_SECRET_ACCESS_KEY")
"""


def test_random_string_vars():
    assert read_env(random_string_vars) == {
        "AWS_ACCESS_KEY_ID": "__REQUIRED__",
        "AWS_SECRET_ACCESS_KEY": "__REQUIRED__",
    }


more_than_one_argument = """
from pathlib import Path
from typing import Optional

from pydantic import Field
from utils.env.base_settings import RANDOM_STRING, BaseEnvVars


class VcHookSettings(BaseEnvVars):
    class Config:
        env_prefix = "vc_hook_"

    gl_token: str = Field(env="GL_TOKEN", default=RANDOM_STRING)
    gl_header_token: str = Field(default=None)
    pants_base: Path = Path("/Users/espen/workspace/ea_pants")
    local_mr_file: Optional[Path] = None
"""


def test_more_than_one_argument():
    assert read_env(more_than_one_argument) == {
        "GL_TOKEN": "__REQUIRED__",
        "vc_hook_gl_header_token": "None",
        "vc_hook_local_mr_file": "None",
        "vc_hook_pants_base": "/Users/espen/workspace/ea_pants",
    }


list_default_arg = """

class VcHookSettings(BaseEnvVars):
    class Config:
        env_prefix = "vc_hook_"
    lib_repo_urls: List[str] = []
"""


def test_list_default_arg():
    assert read_env(list_default_arg) == {"vc_hook_lib_repo_urls": "[]"}


settings_with_port = """
from utils.env.base_settings import BaseEnvVars, port_info

class VcHookSettings(BaseEnvVars):
    class Config:
        env_prefix = "vc_hook_"
    port: int = port_info(8001, url_prefix="/", protocol="http")

"""


def test_settings_with_port():
    env, ports = read_env_and_ports(settings_with_port)
    assert env == {"vc_hook_port": "8001"}
    assert ports == [PrefixPort(prefix="/", port=8001, protocol="http")]


settings_with_default_factory = """
class VcHookSettings(BaseEnvVars):
    pipelines: Dict[TriggerUrl, Dict[str, List[PipelineStep]]] = Field(
        default_factory=dict
    )"""


def test_settings_with_default_factory():
    env, _ = read_env_and_ports(settings_with_default_factory)
    assert env == {"pipelines": "__FACTORY__dict"}


class_not_subclassing_BaseEnvVars = """
class TriggerUrl(NamedTuple):
    trigger: VcTrigger
    url: str
"""


def test_class_not_subclassing_BaseEnvVars_should_not_generate_env_vars():
    env, _ = read_env_and_ports(class_not_subclassing_BaseEnvVars)
    assert env == {}


settings_env_no_default = """
from pydantic import Field
from utils.env.base_settings import BaseEnvVars


class ComposePytestSettings(BaseEnvVars):
    #: Needed to not use folder name as the project name see
    # https://docs.docker.com/compose/reference/overview/#use--p-to-specify-a-project-name
    compose_project_name: str = Field(env="COMPOSE_PROJECT_NAME")
"""


def test_settings_env_no_default():
    env, _ = read_env_and_ports(settings_env_no_default)
    assert env == {"COMPOSE_PROJECT_NAME": "__REQUIRED__"}


settings_with_lambda = """
class WebSettings(BaseEnvVars):
    class Config:
        env_prefix = "web_"

    users_and_passwords: Dict[str, str] = Field(
        default_factory=lambda: dict(default="default")
    )
"""


def test_settings_with_lambda():
    env, _ = read_env_and_ports(settings_with_lambda)
    assert env == {"web_users_and_passwords": "__FACTORY__lambda"}


settings_with_unknown = """
class SeleniumTestSettings(BaseEnvVars):
    class Config:
        env_prefix = "selenium_"

    mongo_url: str = UNKNOWN
"""


def test_settings_with_unknown():
    env, _ = read_env_and_ports(settings_with_unknown)
    assert env == {"selenium_mongo_url": "__REQUIRED__"}


settings_with_global_constants = """
from pathlib import Path

SECONDS_IN_ONE_DAY = 3600 * 24
LAST_TS_DEFAULT_PATH = "/capture_state/last_ts.txt"

class CaptureSettings(BaseEnvVars):
    max_s_since_log_message: int = SECONDS_IN_ONE_DAY
    log_ts_path: Path = Path(LAST_TS_DEFAULT_PATH)
"""


def test_settings_with_global_constants():
    env, _ = read_env_and_ports(settings_with_global_constants)
    assert env == {"log_ts_path": REQUIRED, "max_s_since_log_message": REQUIRED}


def test_settings_with_skip_settings():
    env, _ = read_env_and_ports(
        settings_with_global_constants, skip_settings={"CaptureSettings"}
    )
    assert env == {}


settings_with_classvars = """
class BuildEc2StarterSettings(BaseEnvVars):
    repo_path: Path = Path("/repos/infra")
    ssh_path: Path = Path("/ssh/aws-ec2-builder.pem")
    tfe_token: str = Field(env="TFE_TOKEN")

    CLONE_URL: ClassVar[str] = "https://gitlab.com/wheelme/deploy/infra"
    TERRAGRUNT_DIR: ClassVar[str] = "clusters/eu-west-1/dev3/aws-ec2-builder"

    @property
    def terraform_dir(self) -> Path:
        return self.repo_path / self.TERRAGRUNT_DIR
"""


def test_settings_with_class_vars():
    env, _ = read_env_and_ports(settings_with_classvars)
    assert env == {
        "TFE_TOKEN": "__REQUIRED__",
        "repo_path": "/repos/infra",
        "ssh_path": "/ssh/aws-ec2-builder.pem",
    }
