from itertools import chain
from pathlib import Path, PurePath
from tempfile import TemporaryDirectory
from typing import Optional

from compose_chart_export.compose_export import export_from_compose
from compose_chart_export.ports import PrefixPort
from pants.backend.docker.target_types import DockerImageTagsField, DockerImageTarget
from pants.backend.python.target_types import PythonSourceField
from pants.core.goals.fix import FixFilesRequest, FixResult, Partitions
from pants.core.util_rules.source_files import SourceFiles, SourceFilesRequest
from pants.engine.collection import Collection
from pants.engine.fs import (
    CreateDigest,
    Digest,
    DigestContents,
    DigestSubset,
    FileContent,
    PathGlobs,
)
from pants.engine.internals.native_engine import Snapshot
from pants.engine.internals.selectors import Get, MultiGet
from pants.engine.rules import collect_rules, rule
from pants.engine.target import AllTargets, TransitiveTargets, TransitiveTargetsRequest
from pants.util.frozendict import FrozenDict
from pants.util.meta import classproperty
from pants.util.ordered_set import FrozenOrderedSet
from pants_py_deploy.compose_file import (
    as_compose_yaml,
    as_new_compose_yaml,
    combined_ports,
    create_compose_files,
    file_env_vars,
    modify_existing_compose,
)
from pants_py_deploy.export_env import read_env_and_ports
from pants_py_deploy.fields import (
    ComposeChartField,
    ComposeChartNameField,
    ComposeEnabledField,
)
from pants_py_deploy.models import (
    ComposeExportChart,
    ComposeExportChartRequest,
    ComposeFiles,
    ComposeService,
    ComposeServiceRequest,
    EnvVar,
    FileEnvVars,
    HelmChartsExported,
)
from zero_3rdparty.file_utils import iter_paths_and_relative
from zero_3rdparty.str_utils import ensure_suffix


class DockerComposeFileFixer(FixFilesRequest):
    @classproperty
    def tool_name(cls) -> str:
        return "docker-compose"

    @classproperty
    def tool_id(cls) -> str:
        return "dockercompose"


class HelmChartFileFixer(FixFilesRequest):
    @classproperty
    def tool_name(cls) -> str:
        return "helm-chart"

    @classproperty
    def tool_id(cls) -> str:
        return "helmchart"


@rule
async def export_helm_charts(compose_files: ComposeFiles) -> HelmChartsExported:
    requests = []
    for chart_path, service in compose_files.helm_charts.items():
        requests.append(
            Get(ComposeExportChart, ComposeExportChartRequest(service, chart_path))
        )
    exports = await MultiGet(requests)
    charts = {export.chart_path: export.files for export in exports}
    return HelmChartsExported(charts)


def as_chart_version(image_tag: str) -> str:
    """
    >>> as_chart_version('0.0.1-latest-amd')
    '0.0.1-latest-chart'
    """
    return ensure_suffix(image_tag.removesuffix("-amd").removesuffix("-arm"), "-chart")


@rule
async def export_helm_chart(request: ComposeExportChartRequest) -> ComposeExportChart:
    chart_yaml_path = request.chart_path
    chart_path = PurePath(chart_yaml_path).parent
    chart_digest: Optional[DigestContents] = None

    def store_digest(exported_chart_path: Path):
        nonlocal chart_digest
        file_contents = []
        for path, relative_path in iter_paths_and_relative(
            exported_chart_path, "*", rglob=True
        ):
            if path.is_dir():
                continue
            file_contents.append(
                FileContent(
                    path=f"{chart_path}/{relative_path}", content=path.read_bytes()
                )
            )
        chart_digest = DigestContents(file_contents)

    service = request.service
    with TemporaryDirectory() as tmpdir:
        digest = await Get(DigestContents, PathGlobs([service.path]))
        if digest:
            compose_yaml = as_compose_yaml([service], digest[0])
        else:
            compose_yaml = as_new_compose_yaml([service])
        docker_compose_path = Path(tmpdir) / "docker-compose.yaml"
        docker_compose_path.write_text(compose_yaml)
        export_from_compose(
            compose_path=docker_compose_path,
            chart_version=as_chart_version(service.image_tag),
            chart_name=service.chart_inferred_name,
            image_url=service.image_url,
            on_exported=store_digest,
        )
    assert chart_digest
    return ComposeExportChart(chart_path=chart_yaml_path, files=chart_digest)


@rule
async def docker_compose_partition(
    request: DockerComposeFileFixer.PartitionRequest, compose_files: ComposeFiles
) -> Partitions:
    managed_files = list(compose_files.paths_managed.keys())
    input_digest = [
        file for file in request.files if PurePath(file).stem == "docker-compose"
    ]
    return Partitions.single_partition(set(input_digest + managed_files))


@rule
async def helm_chart_partition(
    request: HelmChartFileFixer.PartitionRequest,
    new_exported_charts: HelmChartsExported,
) -> Partitions:
    managed_chart_files = list(
        file.path for file in chain.from_iterable(new_exported_charts.charts.values())
    )
    return Partitions.single_partition(managed_chart_files)


@rule
async def find_env_vars(targets: AllTargets) -> FileEnvVars:
    # don't understand why targets: Targets doesn't work
    sources = await Get(
        SourceFiles,
        SourceFilesRequest(
            [
                target[PythonSourceField]
                for target in targets
                if target.has_field(PythonSourceField)
            ]
        ),
    )

    settings_digest = await Get(
        Digest, DigestSubset(sources.snapshot.digest, PathGlobs(["**/settings.py"]))
    )
    digest_contents = await Get(DigestContents, Digest, settings_digest)
    file_env_vars_ports = {
        file_content.path: read_env_and_ports(
            py_script=file_content.content.decode("utf-8")
        )
        for file_content in digest_contents
    }
    file_env_vars = {
        file: [EnvVar(name, default) for name, default in env_vars.items()]
        for file, (env_vars, _) in file_env_vars_ports.items()
    }
    file_ports = {file: ports for file, (_, ports) in file_env_vars_ports.items()}
    return FileEnvVars(file_env_vars, file_ports)


@rule
async def resolve_compose_service(
    service_request: ComposeServiceRequest, all_env_vars: FileEnvVars
) -> ComposeService:
    image = service_request.image
    transitive_targets = await Get(
        TransitiveTargets, TransitiveTargetsRequest([image.address])
    )
    spec_path = image.address.spec_path
    dependencies = [str(dep.address) for dep in transitive_targets.dependencies]
    image_tag = image[DockerImageTagsField].value[0]
    compose_chart_relative_path = service_request.image.get(
        ComposeChartField, default_raw_value=""
    ).value
    if compose_chart_relative_path:
        chart_path = ensure_suffix(
            f"{spec_path}/{compose_chart_relative_path}", "/Chart.yaml"
        )
    else:
        chart_path = ""
    return ComposeService(
        path=ensure_suffix(spec_path, "/docker-compose.yaml"),
        name=image.address.target_name,
        dependency_paths=FrozenOrderedSet(dependencies),
        env_vars=FrozenDict(file_env_vars(all_env_vars, dependencies)),
        ports=Collection[PrefixPort](combined_ports(all_env_vars, dependencies)),
        image_tag=image_tag,
        chart_path=chart_path,
        chart_name=image.get(ComposeChartNameField, default_raw_value="").value,
    )


@rule
async def find_managed_compose_files_with_sources(targets: AllTargets) -> ComposeFiles:
    compose_targets: list[DockerImageTarget] = [
        target
        for target in targets
        if target.get(ComposeEnabledField, default_raw_value=False).value
    ]
    compose_services = await MultiGet(
        [
            Get(ComposeService, ComposeServiceRequest(image=target))
            for target in compose_targets
        ]
    )
    return ComposeFiles(
        compose_services,
    )


@rule
async def fix_docker_compose(
    request: DockerComposeFileFixer.Batch,
    compose_files: ComposeFiles,
) -> FixResult:
    input_snapshot = request.snapshot
    digest_contents = await Get(DigestContents, Digest, input_snapshot.digest)
    updated_contents = modify_existing_compose(compose_files, digest_contents)
    updates_paths = {file_content.path for file_content in updated_contents}
    new_files = compose_files.paths_managed.keys() - updates_paths
    new_contents = create_compose_files(new_files, compose_files)
    all_contents = updated_contents + new_contents
    output_snapshot = await Get(Snapshot, CreateDigest(all_contents))
    return FixResult(
        input=input_snapshot,
        output=output_snapshot,
        stdout="",
        stderr="",
        tool_name=DockerComposeFileFixer.tool_name,
    )


@rule
async def fix_helm_charts(
    request: HelmChartFileFixer.Batch, charts: HelmChartsExported
) -> FixResult:
    batch_files = set(request.files)
    out_files = [
        file_content
        for file_content in charts.full_digest
        if file_content.path in batch_files
    ]
    new_contents = await Get(Snapshot, CreateDigest(out_files))
    return FixResult(
        input=request.snapshot,
        output=new_contents,
        stderr="",
        stdout="",
        tool_name=HelmChartFileFixer.tool_name,
    )


def rules():
    return [
        *collect_rules(),
        *DockerComposeFileFixer.rules(),
        *HelmChartFileFixer.rules(),
        find_env_vars,
    ]
