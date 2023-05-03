from collections import defaultdict
from dataclasses import dataclass
from itertools import chain
from typing import Iterable

from compose_chart_export.ports import PrefixPort
from pants.backend.docker.target_types import DockerImageTarget
from pants.engine.collection import Collection
from pants.engine.fs import DigestContents
from pants.util.frozendict import FrozenDict
from pants.util.ordered_set import FrozenOrderedSet


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
    env_vars: FrozenDict[str, str]
    ports: Collection[PrefixPort]
    image_tag: str
    chart_path: str = ""
    chart_name: str = ""

    @property
    def image_url(self) -> str:
        return f"{self.name}:{self.image_tag}"

    @property
    def chart_inferred_name(self):
        return self.chart_name or self.name


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

    @property
    def helm_charts(self) -> dict[str, ComposeService]:
        return {
            path: service
            for service in chain.from_iterable(self.paths_managed.values())
            if (path := service.chart_path)
        }


@dataclass(frozen=True)
class ComposeServiceRequest:
    image: DockerImageTarget


@dataclass(frozen=True)
class HelmChartsExported:
    # chart paths always is to the Chart.yaml file
    charts: FrozenDict[str, DigestContents]

    def __init__(self, charts: dict[str, DigestContents]):
        """Expecting FileContent to have the full relative path.

        Keys are path to the chart itself
        """
        object.__setattr__(self, "charts", FrozenDict(charts))

    @property
    def full_digest(self) -> DigestContents:
        return DigestContents(chain.from_iterable(self.charts.values()))


@dataclass(frozen=True)
class ComposeExportChartRequest:
    # chart paths always is to the Chart.yaml file
    service: ComposeService
    chart_path: str


@dataclass(frozen=True)
class ComposeExportChart:
    chart_path: str
    files: DigestContents
