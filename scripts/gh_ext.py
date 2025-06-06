from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property, lru_cache, total_ordering, wraps
from pathlib import Path
from typing import Any, Callable, ClassVar, Generic, Protocol, Self, TypeVar

import git
import typer
from ask_shell._run import run_and_wait
from ask_shell._run_env import interactive_shell
from ask_shell.interactive2 import select_list_multiple
from ask_shell.rich_live import print_to_live_console
from ask_shell.rich_progress import new_task
from ask_shell.settings import AskShellSettings
from ask_shell.typer_command import configure_logging
from model_lib import Entity, parse_payload
from model_lib.serialize import dump
from model_lib.serialize.parse import parse_model
from model_lib.static_settings import StaticSettings
from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator
from pydantic_core import Url
from rich.markdown import Markdown
from zero_3rdparty import dict_nested, file_utils, iter_utils
from zero_3rdparty.datetime_utils import utc_now


def find_owner_project(repo: git.Repo) -> str:
    remote = next((remote for remote in repo.remotes if remote.name == "origin"), None)
    assert remote, "No origin remote found"
    remote_url = remote.url
    if "@" in remote_url:
        remote_url = remote_url.split("@")[1]
    url = Url(remote_url)
    url_path = url.path
    assert url_path, f"URL path is empty for {remote_url}"
    return url_path.strip("/").removesuffix(".git")


app = typer.Typer(name="gh-ext", help="GitHub extension commands")
logger = logging.getLogger(__name__)


@lru_cache
def ensure_yaml_parsing_bool_parsing_works_as_expected():
    from yaml.resolver import Resolver

    for ch in "OoYyNn":
        if len(Resolver.yaml_implicit_resolvers[ch]) == 1:
            del Resolver.yaml_implicit_resolvers[ch]
        else:
            Resolver.yaml_implicit_resolvers[ch] = [
                x
                for x in Resolver.yaml_implicit_resolvers[ch]
                if x[0] != "tag:yaml.org,2002:bool"
            ]


class GhExtSettings(StaticSettings):
    def repo_files_dir(self, owner_project: str) -> Path:
        return self.static_root / owner_project

    def repo_export_path(self, owner_project: str) -> Path:
        return self.repo_files_dir(owner_project) / "gh-ext-export.yaml"

    def repo_secrets_path(self, owner_project: str) -> Path:
        """Dictionary of secrets with values, not encrypted, useful to validate you have a backup before deleting secrets."""
        return self.repo_files_dir(owner_project) / "gh-secrets.dec.yaml"


@total_ordering
class GhVarOrSecret(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str
    updated_at: datetime = Field(alias="updatedAt")
    deleted: bool = False
    deleted_ts: datetime | None = None

    def mark_deleted(self) -> None:
        if self.deleted:
            return  # already deleted
        self.deleted = True
        self.deleted_ts = utc_now()

    def __lt__(self, other) -> bool:
        if not isinstance(other, GhVarOrSecret):
            raise TypeError(f"Cannot compare {type(self)} with {type(other)}")
        return (self.deleted, self.name) < (other.deleted, other.name)

    def update(self, other: GhVarOrSecret) -> None:
        if self.name != other.name:
            raise ValueError(
                f"Cannot update {self.__class__.__name__} {self.name} with {other.name}"
            )
        self.updated_at = other.updated_at

    @classmethod
    def get_changes(
        cls, old: list[GhVarOrSecretT], new: list[GhVarOrSecretT]
    ) -> GhVarOrSecretChanges[GhVarOrSecretT]:
        old_dict = var_list_to_dict(old)
        new_dict = var_list_to_dict(new)
        return GhVarOrSecretChanges(
            added=[value for name, value in new_dict.items() if name not in old_dict],
            updated=[
                new_var
                for name, new_var in new_dict.items()
                if name in old_dict and old_dict[name] != new_var
            ],
            deleted=[
                old_var for name, old_var in old_dict.items() if name not in new_dict
            ],
        )


GhVarOrSecretT = TypeVar("GhVarOrSecretT", bound=GhVarOrSecret)


@dataclass
class GhVarOrSecretChanges(Generic[GhVarOrSecretT]):
    added: list[GhVarOrSecretT]
    updated: list[GhVarOrSecretT]
    deleted: list[GhVarOrSecretT]


def var_list_to_dict(some_list: list[GhVarOrSecretT]) -> dict[str, GhVarOrSecretT]:
    return {var.name: var for var in some_list}


class GhVar(GhVarOrSecret):
    value: str

    def update(self, other: GhVarOrSecret) -> None:
        assert isinstance(other, GhVar)
        super().update(other)
        self.value = other.value


class GhSecret(GhVarOrSecret):
    pass


class UpdateMethod(Protocol):
    def __call__(self, self_: GhExtExport, *args: Any, **kwargs: Any) -> None: ...


T = TypeVar("T", bound=Callable)


def ensure_disk_path_updated(func: T) -> T:
    @wraps(func)
    def wrapper(self_: GhExtExport, *args: Any, **kwargs: Any) -> Any:
        try:
            return func(self_, *args, **kwargs)
        except BaseException as e:
            raise e
        finally:
            file_ext = self_.disk_path.suffix
            assert file_ext in (".yaml", ".yml"), (
                "Disk path must have .yaml or .yml extension"
            )
            yaml_text = dump(self_, "yaml")
            file_utils.ensure_parents_write_text(self_.disk_path, yaml_text)

    return wrapper  # type: ignore


class GhExtExport(BaseModel):
    variables: list[GhVar] = Field(default_factory=list)
    secrets: list[GhSecret] = Field(default_factory=list)
    disk_path: Path

    @ensure_disk_path_updated
    def update_variables(self, new_variables: list[GhVar]) -> None:
        self._sync_list_changes(self.variables, new_variables)

    def _sync_list_changes(
        self, exported_list: list[GhVarOrSecretT], new_list: list[GhVarOrSecretT]
    ):
        changes = GhVarOrSecret.get_changes(exported_list, new_list)
        old_dict = var_list_to_dict(exported_list)
        if added := changes.added:
            exported_list.extend(added)
        if deleted := changes.deleted:
            for var in deleted:
                old_var = old_dict[var.name]
                old_var.mark_deleted()
        if updated := changes.updated:
            for var in updated:
                old_var = old_dict[var.name]
                old_var.update(old_var)

    @ensure_disk_path_updated
    def update_secrets(self, new_secrets: list[GhSecret]) -> None:
        self._sync_list_changes(self.secrets, new_secrets)

    @ensure_disk_path_updated
    def mark_deleted_secret(self, name: str) -> None:
        """Mark a secret as deleted by setting its 'deleted' attribute to True."""
        for secret in self.secrets:
            if secret.name == name:
                secret.mark_deleted()
                return
        raise ValueError(f"Secret with name {name} not found in the export.")

    @ensure_disk_path_updated
    def mark_deleted_variable(self, name: str) -> None:
        """Mark a variable as deleted by setting its 'deleted' attribute to True."""
        for var in self.variables:
            if var.name == name:
                var.mark_deleted()
                return
        raise ValueError(f"Variable with name {name} not found in the export.")


class GhVars(RootModel):
    root: list[GhVar]
    workflow_prefix: ClassVar[str] = "vars"

    @cached_property
    def names(self) -> set[str]:
        return {var.name for var in self.root}

    def unused_dict(self, unused: list[str]) -> dict[str, str]:
        """Returns a dictionary of unused variables with their values."""
        return {var.name: var.value for var in self.root if var.name in unused}


class GhSecrets(RootModel):
    root: list[GhSecret]
    workflow_prefix: ClassVar[str] = "secrets"

    @cached_property
    def names(self) -> set[str]:
        return {secret.name for secret in self.root}


@app.command()
def gh_vars_usage(
    path: str = typer.Argument(
        ..., help="Path to a repository, use $(pwd) to get current path"
    ),
    show_unused_values: bool = typer.Option(
        False,
        "--show-unused-values",
        "-suv",
        help="Show values of unused variables (secrets cannot be shown)",
    ),
    report_path: str = typer.Option(
        "gh-ext-vars-usage.md",
        "--report-path",
        "--rp",
        help="Relative path from repo root to save the report or absolute path, default: gh-ext-vars-usage.md, use '' to disable",
    ),
    print_report: bool = typer.Option(
        False,
        "--print",
        help="Print the report to stdout",
    ),
    delete_unused: bool = typer.Option(
        False,
        "--delete",
        help="Delete unused variables and secrets (prompted if running interactively)",
    ),
    delete_safe: bool = typer.Option(
        False,
        "--delete-safe",
        help="Will only delete secrets where a local value is available. This is useful to ensure you have a backup before deleting the secrets.",
    ),
):
    if delete_safe and not delete_unused:
        delete_unused = True
    if delete_unused and not interactive_shell():
        raise ValueError(
            "Cannot delete unused variables and secrets in non-interactive shell"
        )
    ctx = CreateVariableSecretReportContext.from_cli(
        path=path,
        show_unused_values=show_unused_values,
        report_path=report_path,
        delete_safe=delete_safe,
    )
    result = create_variable_secret_report(ctx)
    if print_report or delete_unused:
        print_to_live_console(Markdown(result.report_or_ok))
    if unused_vars := result.unused_vars:
        unused_var_names = list(unused_vars)
        vars_to_delete = select_list_multiple(
            "Select unused variables to delete",
            choices=unused_var_names,
            default=unused_var_names,
        )
        delete_vars(vars_to_delete, ctx)
    if unused_secrets := result.unused_secrets:
        secrets_to_delete = select_list_multiple(
            "Select unused secrets to delete",
            choices=unused_secrets,
            default=unused_secrets,
        )
        delete_secrets(secrets_to_delete, ctx)


def delete_vars(vars_to_delete: list[str], ctx: CreateVariableSecretReportContext):
    for var_name in vars_to_delete:
        command = f"gh variable delete -R {ctx.owner_project} {var_name}"
        run_and_wait(command, cwd=ctx.repo_path, user_input=True)
        ctx.export.mark_deleted_variable(var_name)


def delete_secrets(
    secrets_to_delete: list[str], ctx: CreateVariableSecretReportContext
):
    restorable_secrets = restoreable_secrets(ctx)
    secrets_path = ctx.gh_ext_settings.repo_secrets_path(ctx.owner_project)
    for secret_name in secrets_to_delete:
        command = f"gh secret delete -R {ctx.owner_project} {secret_name}"
        if ctx.delete_safe and secret_name not in restorable_secrets:
            logger.warning(
                f"Skipping deletion of secret {secret_name} as it is not restorable (not found in {secrets_path})"
            )
            continue
        run_and_wait(command, cwd=ctx.repo_path, user_input=True)
        ctx.export.mark_deleted_secret(secret_name)


def restoreable_secrets(ctx: CreateVariableSecretReportContext) -> set[str]:
    secret_disk_path = ctx.gh_ext_settings.repo_secrets_path(ctx.owner_project)
    if not secret_disk_path.exists():
        return set()
    secrets = parse_payload(secret_disk_path)
    assert isinstance(secrets, dict), "Secrets should be a dictionary"
    return set(secrets.keys())


class CreateVariableSecretReportContext(Entity):
    show_unused_values: bool = False
    report_path: str = "gh-ext-vars-usage.md"
    repo_path: Path
    call_path: Path
    owner_project: str
    shell_settings: AskShellSettings = Field(default_factory=AskShellSettings.from_env)
    gh_ext_settings: GhExtSettings = Field(default_factory=GhExtSettings.from_env)
    export: GhExtExport = Field(init=False, default=None)  # type: ignore
    delete_safe: bool = False

    @model_validator(mode="after")
    def read_or_create_export(self) -> Self:
        owner_project = self.owner_project
        export_path = self.gh_ext_settings.repo_export_path(owner_project)
        if export_path.exists():
            self.export = parse_model(export_path, GhExtExport)
        else:
            self.export = GhExtExport(disk_path=export_path)
        return self

    @cached_property
    def repo(self) -> git.Repo:
        return git.Repo(self.repo_path, search_parent_directories=True)

    @property
    def report_path_abs(self) -> Path | None:
        if self.report_path == "":
            return None
        if self.report_path.startswith("/"):
            return Path(self.report_path)
        return self.repo_path / self.report_path

    @classmethod
    def from_cli(
        cls, path: str, show_unused_values: bool, report_path: str, delete_safe: bool
    ) -> Self:
        maybe_nested_dir = Path(path)
        assert maybe_nested_dir.exists(), f"Repo dir does not exist: {maybe_nested_dir}"
        repo = git.Repo(maybe_nested_dir, search_parent_directories=True)
        owner_project = find_owner_project(repo)
        working_dir = repo.working_tree_dir
        assert working_dir, f"Cannot find git directory for {maybe_nested_dir}"
        repo_dir = Path(working_dir)
        assert repo_dir, f"Cannot find git directory for {maybe_nested_dir}"
        return cls(
            show_unused_values=show_unused_values,
            report_path=report_path,
            repo_path=repo_dir,
            call_path=repo_dir,
            owner_project=owner_project,
            delete_safe=delete_safe,
        )


class CreateVariableSecretReportContextOutput(BaseModel):
    report_md: str = ""
    unused_vars: dict[str, str] = Field(default_factory=dict)
    unused_secrets: list[str] = Field(default_factory=list)

    @property
    def report_or_ok(self) -> str:
        if self.report_md:
            return self.report_md
        return "No unused variables or secrets found 🎉"


def create_variable_secret_report(
    ctx: CreateVariableSecretReportContext,
) -> CreateVariableSecretReportContextOutput:
    repo_dir = ctx.repo_path
    owner_project = ctx.owner_project

    token_run = run_and_wait("gh auth token", cwd=repo_dir)
    token = token_run.stdout
    assert token, "Token is empty"
    report_md: list[str] = []
    out_event = CreateVariableSecretReportContextOutput()

    vars_out = run_and_wait(
        f"gh variable list -R {owner_project} --json name,value,updatedAt"
    )
    vars_json = parse_payload(vars_out.stdout, "json")
    if vars_json:
        gh_vars = GhVars(root=vars_json)  # type: ignore
        ctx.export.update_variables(gh_vars.root)
        vars_lines, unused_vars = create_md_usage_report(ctx, gh_vars, find_vars_usages)
        out_event.unused_vars = gh_vars.unused_dict(unused_vars)
        report_md.extend(vars_lines)
    else:
        logger.warning("No variables found")
    secrets_out = run_and_wait(
        f"gh secret list -R {owner_project} --json name,updatedAt"
    )
    if secrets_json := parse_payload(secrets_out.stdout, "json"):
        gh_secrets = GhSecrets(root=secrets_json)  # type: ignore
        ctx.export.update_secrets(gh_secrets.root)
        if report_md:
            report_md.append("\n\n")  # add extra new lines between vars and secrets
        secret_lines, unused_secrets = create_md_usage_report(
            ctx, gh_secrets, find_secrets_usages
        )
        report_md.extend(secret_lines)
        out_event.unused_secrets = unused_secrets
    else:
        logger.warning("No secrets found")
    report_content = out_event.report_md = "\n".join(report_md)
    report_path = ctx.report_path_abs
    if not report_path or not report_content:
        return out_event
    report_md.append("")  # end with a new line
    file_utils.ensure_parents_write_text(report_path, report_content)
    return out_event


def create_md_usage_report(
    event_in: CreateVariableSecretReportContext,
    gh_vars: GhVars | GhSecrets,
    find_usages: Callable[[str], set[str]],
) -> tuple[list[str], list[str]]:
    repo_dir = event_in.repo_path
    repo = event_in.repo
    header = f"# GH {gh_vars.workflow_prefix.capitalize()}"
    report_md: list[str] = []
    used_vars, not_found_errors = collect_used_names(repo_dir, gh_vars, find_usages)
    if not_found_errors:
        report_md.extend((header, "## Not Found"))
        report_md.extend(sorted(not_found_errors))
    if unused_vars := gh_vars.names - used_vars:
        if not report_md:
            report_md.append(header)
        report_md.append("\n## Unused")
        if event_in.show_unused_values and isinstance(gh_vars, GhVars):
            unused_lines = sorted(
                f"- {var.name}=`{var.value}`"
                for var in gh_vars.root
                if var.name in unused_vars
            )
        else:
            unused_lines = sorted(f"- {var}" for var in unused_vars)
        report_md.extend(unused_lines)
        if usages := find_names_usage(
            repo,
            repo_dir,
            unused_vars,
            header,
        ):
            report_md.append("\n### Unused Usages In Repo")
            report_md.extend(sorted(usages))
        return report_md, sorted(unused_vars)
    return report_md, []


def collect_used_names(
    repo_dir: Path, gh_vars: GhVars | GhSecrets, find_usages: Callable[[str], set[str]]
) -> tuple[set[str], list[str]]:
    used_vars: set[str] = set()
    vars_not_found_errors: list[str] = []
    gh_vars_names = gh_vars.names
    for yml_path, rel_path in file_utils.iter_paths_and_relative(
        repo_dir / ".github/workflows", "*.yml", "*.yaml", only_files=True
    ):
        path_vars_uses = find_usages(yml_path.read_text())
        used_vars |= path_vars_uses
        if not_found := path_vars_uses - gh_vars_names:
            vars_not_found_errors.append(
                f"- File: {rel_path}, not found {gh_vars.workflow_prefix}: {', '.join(sorted(not_found))}"
            )

    return used_vars, vars_not_found_errors


def find_names_usage(
    repo: git.Repo,
    repo_dir: Path,
    unused_vars: set[str],
    header: str,
) -> list[str]:
    unused_vars_name_usage: list[str] = []
    unused_name_pattern = names_pattern(unused_vars)
    files_in_repo = [
        (file_path, rel_path)
        for file_path, rel_path in file_utils.iter_paths_and_relative(
            repo_dir, "*", only_files=True
        )
        if not (
            rel_path.startswith(".")
            or "/." in rel_path
            or rel_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico"))
        )
    ]
    filtering_time = len(files_in_repo) // 1000
    with new_task(
        f"Finding files to look for usages of {len(unused_vars)} unused {header} in repo",
        total=len(files_in_repo) + filtering_time,
    ) as find_files:
        rel_paths = [rel_path for _, rel_path in files_in_repo]
        ignored_files = set()
        for rel_paths_slice in iter_utils.iter_slices(rel_paths, max=1000):
            ignored_files |= set(
                repo.ignored(*rel_paths_slice)
            )  # performance optimization calling repo.ignored() only per 1000 files
            find_files.update(advance=len(rel_paths_slice))
        files_in_repo = [
            (file_path, rel_path)
            for file_path, rel_path in files_in_repo
            if rel_path not in ignored_files
        ]
        find_files.update(advance=filtering_time)
        total_files = len(files_in_repo)
    with new_task(
        f"Looking for usages of {len(unused_vars)} unused {header} in {total_files} files",
        total=total_files,
    ) as look_for_usages:
        for file_path, rel_path in files_in_repo:
            look_for_usages.update(advance=1)
            try:
                file_text = file_path.read_text()
            except UnicodeDecodeError:
                logger.warning(f"Cannot read file: {file_path}, skipping")
                continue
            if name_uses := find_names_usages(unused_name_pattern, file_text):
                unused_vars_name_usage.append(
                    f"File: {rel_path}, used vars: {', '.join(sorted(name_uses))}"
                )
        return sorted(unused_vars_name_usage)


vars_pattern = re.compile(rf"{GhVars.workflow_prefix}\.(?P<var_name>\w+)")
secrets_pattern = re.compile(rf"{GhSecrets.workflow_prefix}\.(?P<var_name>\w+)")


def find_vars_usages(yml_text: str) -> set[str]:
    return {match.group("var_name") for match in vars_pattern.finditer(yml_text)}


def find_secrets_usages(yml_text: str) -> set[str]:
    all_found = {
        match.group("var_name") for match in secrets_pattern.finditer(yml_text)
    }
    return all_found - find_input_secrets(yml_text)


def find_input_secrets(yml_text: str) -> set[str]:
    ensure_yaml_parsing_bool_parsing_works_as_expected()  # to ensure on is parsed as a string
    parsed_file = parse_payload(yml_text, "yaml")
    workflow_call_secrets = dict_nested.read_nested_or_none(
        parsed_file, "on.workflow_call.secrets"
    )
    secrets = {"GITHUB_TOKEN"}
    if isinstance(workflow_call_secrets, dict):
        secrets |= workflow_call_secrets.keys()
    return secrets


def names_pattern(names: set[str]) -> re.Pattern:
    return re.compile(rf"(?<!\w)({'|'.join(sorted(names))})(?!\w)")


def find_names_usages(pattern: re.Pattern, text: str) -> set[str]:
    return {match.group(0) for match in pattern.finditer(text)}


def main():
    configure_logging(app)
    app()


if __name__ == "__main__":
    main()
