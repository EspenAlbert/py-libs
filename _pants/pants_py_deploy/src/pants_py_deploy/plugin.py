from dataclasses import dataclass
from pathlib import PurePath

from pants.backend.docker.target_types import DockerImageTagsField, DockerImageTarget
from pants.backend.python.target_types import PythonSourceField
from pants.core.goals.fix import FixFilesRequest, FixResult, Partitions
from pants.core.util_rules.source_files import SourceFiles, SourceFilesRequest
from pants.engine.fs import (
    CreateDigest,
    Digest,
    DigestContents,
    DigestSubset,
    PathGlobs,
)
from pants.engine.internals.native_engine import Snapshot
from pants.engine.internals.selectors import Get, MultiGet
from pants.engine.rules import collect_rules, rule
from pants.engine.target import (
    AllTargets,
    FieldSet,
    TransitiveTargets,
    TransitiveTargetsRequest,
)
from pants.util.meta import classproperty
from pants.util.ordered_set import FrozenOrderedSet
from pants_py_deploy.compose_file import create_compose_files, modify_existing_compose
from pants_py_deploy.export_env import read_env_and_ports
from pants_py_deploy.fields import ComposeEnabledField
from pants_py_deploy.models import (
    ComposeFiles,
    ComposeService,
    ComposeServiceRequest,
    EnvVar,
    FileEnvVars,
)
from zero_3rdparty.str_utils import ensure_suffix


@dataclass(frozen=True)
class DockerComposeFieldSet(FieldSet):
    required_fields = (PythonSourceField,)

    source: PythonSourceField


#
#
class DockerComposeFileFixer(FixFilesRequest):
    """Ensures all non-comment lines only consist of the word 'brick'."""

    field_set_type = DockerComposeFieldSet

    @classproperty
    def tool_name(cls) -> str:
        return "docker-compose"

    @classproperty
    def tool_id(cls) -> str:
        return "dockercompose"


@rule
async def docker_compose_partition(
    request: DockerComposeFileFixer.PartitionRequest, compose_files: ComposeFiles
) -> Partitions:
    managed_files = [path for path in compose_files.paths_managed.keys()]
    input_digest = [
        file for file in request.files if PurePath(file).stem == "docker-compose"
    ]
    return Partitions.single_partition(set(input_digest + managed_files))


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
    service_request: ComposeServiceRequest,
) -> ComposeService:
    image = service_request.image
    transitive_targets = await Get(
        TransitiveTargets, TransitiveTargetsRequest([image.address])
    )
    path = image.address.spec_path
    dependencies = [str(dep.address) for dep in transitive_targets.dependencies]
    image_tag = image[DockerImageTagsField].value[0]
    return ComposeService(
        path=ensure_suffix(path, "/docker-compose.yaml"),
        name=image.address.target_name,
        dependency_paths=FrozenOrderedSet(dependencies),
        image_tag=image_tag,
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
    return ComposeFiles(compose_services)


@rule
async def fix_docker_compose(
    request: DockerComposeFileFixer.Batch,
    env_vars: FileEnvVars,
    compose_files: ComposeFiles,
) -> FixResult:
    input_snapshot = request.snapshot
    digest_contents = await Get(DigestContents, Digest, input_snapshot.digest)
    updated_contents = modify_existing_compose(compose_files, digest_contents, env_vars)
    updates_paths = {file_content.path for file_content in updated_contents}
    new_files = compose_files.paths_managed.keys() - updates_paths
    new_contents = create_compose_files(new_files, env_vars, compose_files)
    all_contents = updated_contents + new_contents
    output_snapshot = await Get(Snapshot, CreateDigest(all_contents))
    return FixResult(
        input=input_snapshot,
        output=output_snapshot,
        stdout="",
        stderr="",
        tool_name=DockerComposeFileFixer.tool_name,
    )


def rules():
    return [*collect_rules(), *DockerComposeFileFixer.rules(), find_env_vars]
