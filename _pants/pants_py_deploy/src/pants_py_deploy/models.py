from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from pants.backend.docker.target_types import DockerImageTarget
from pants.engine.collection import Collection
from pants.util.frozendict import FrozenDict
from pants.util.ordered_set import FrozenOrderedSet
from pants_py_deploy.ports import PrefixPort


@dataclass(frozen=True)
class EnvVar:
    name: str
    default: str


@dataclass(frozen=True)
class FileEnvVars:
    file_env_vars: FrozenDict[str, Collection[EnvVar]]
    file_port_info: FrozenDict[str, Collection[PrefixPort]]

    def __init__(
        self,
        file_env_vars: dict[str, Iterable[EnvVar]],
        file_port_info: dict[str, Iterable[PrefixPort]],
    ):
        object.__setattr__(
            self,
            "file_env_vars",
            FrozenDict(
                {
                    key: Collection[EnvVar](env_vars)
                    for key, env_vars in file_env_vars.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "file_port_info",
            FrozenDict(
                {
                    key: Collection[PrefixPort](ports)
                    for key, ports in file_port_info.items()
                }
            ),
        )


@dataclass(frozen=True)
class ComposeService:
    path: str
    name: str
    dependency_paths: FrozenOrderedSet[str]
    image_tag: str

    @property
    def image_url(self) -> str:
        return f"{self.name}:{self.image_tag}"


@dataclass(frozen=True)
class ComposeFiles:
    paths_managed: FrozenDict[str, Collection[ComposeService]]

    def __init__(self, services: Iterable[ComposeService]):
        path_to_service = defaultdict(list)
        for service in services:
            path_to_service[service.path].append(service)
        paths_managed = {
            path: Collection[ComposeService](services)
            for path, services in path_to_service.items()
        }
        object.__setattr__(self, "paths_managed", FrozenDict(paths_managed))

    def is_managed(self, path: str) -> bool:
        return path in self.paths_managed


@dataclass(frozen=True)
class ComposeServiceRequest:
    image: DockerImageTarget
