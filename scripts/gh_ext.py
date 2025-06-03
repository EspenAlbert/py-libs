import logging
import re
import time
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Callable, ClassVar, Self

import git
import typer
from ask_shell._run import run_and_wait
from ask_shell.rich_progress import new_task
from ask_shell.typer_command import configure_logging
from model_lib import Entity, parse_payload
from pydantic import BaseModel, RootModel
from pydantic_core import Url
from zero_3rdparty import dict_nested, file_utils, iter_utils


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


app = typer.Typer()
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


class GhVar(BaseModel):
    name: str
    value: str


class GhSecret(BaseModel):
    name: str


class GhVars(RootModel):
    root: list[GhVar]
    workflow_prefix: ClassVar[str] = "vars"

    @cached_property
    def names(self) -> set[str]:
        return {var.name for var in self.root}


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
):
    ctx = CreateVariableSecretReportContext.from_cli(
        path=path,
        show_unused_values=show_unused_values,
        report_path=report_path,
    )
    report_md = create_variable_secret_report(ctx)
    if print_report:
        time.sleep(3)
        logger.info(f"Markdown report:\n{report_md}")


class CreateVariableSecretReportContext(Entity):
    show_unused_values: bool = False
    report_path: str = "gh-ext-vars-usage.md"
    repo_path: Path
    call_path: Path
    owner_project: str

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
    def from_cli(cls, path: str, show_unused_values: bool, report_path: str) -> Self:
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
        )


def create_variable_secret_report(ctx: CreateVariableSecretReportContext) -> str:
    repo_dir = ctx.repo_path
    owner_project = ctx.owner_project

    token_run = run_and_wait("gh auth token", cwd=repo_dir)
    token = token_run.stdout
    assert token, "Token is empty"
    report_md: list[str] = []

    vars_out = run_and_wait(f"gh variable list -R {owner_project} --json name,value")
    vars_json = parse_payload(vars_out.stdout, "json")
    if vars_json:
        gh_vars = GhVars(root=vars_json)  # type: ignore
        report_md.extend(create_md_usage_report(ctx, gh_vars, find_vars_usages))
    else:
        logger.warning("No variables found")
    secrets_out = run_and_wait(f"gh secret list -R {owner_project} --json name")
    if secrets_json := parse_payload(secrets_out.stdout, "json"):
        gh_secrets = GhSecrets(root=secrets_json)  # type: ignore
        if report_md:
            report_md.append("\n\n")  # add extra new lines between vars and secrets
        report_md.extend(create_md_usage_report(ctx, gh_secrets, find_secrets_usages))
    else:
        logger.warning("No secrets found")
    report_content = "\n".join(report_md)
    report_path = ctx.report_path_abs
    if not report_path or not report_content:
        return report_content
    report_md.append("")  # end with a new line
    file_utils.ensure_parents_write_text(report_path, report_content)
    return report_content


def create_md_usage_report(
    event_in: CreateVariableSecretReportContext,
    gh_vars: GhVars | GhSecrets,
    find_usages: Callable[[str], set[str]],
) -> list[str]:
    repo_dir = event_in.repo_path
    repo = event_in.repo
    header = f"# GH {gh_vars.workflow_prefix.capitalize()}"
    report_md: list[str] = [header]
    used_vars, not_found_errors = collect_used_names(repo_dir, gh_vars, find_usages)
    if not_found_errors:
        report_md.append("## Not Found")
        report_md.extend(sorted(not_found_errors))
    if unused_vars := gh_vars.names - used_vars:
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
    return report_md


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
