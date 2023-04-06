from model_lib.base_settings import BaseEnvVars, env_var_name
from pydantic import Field


class EnvVarsList(BaseEnvVars):
    var4: list[str] = Field(default_factory=list)


def test_env_var_with_list(monkeypatch):
    monkeypatch.setenv(env_var_name(EnvVarsList, "var4"), "value1 value2")
    assert EnvVarsList().var4 == ["value1", "value2"]
