"""Generation commands: gen_examples, gen_tests, gen_docs, dump_api, diff_api."""

import logging
from pathlib import Path

import typer
from model_lib.serialize import dump, parse_model
from zero_3rdparty.file_utils import ensure_parents_write_text

from pkg_ext import api_diff
from pkg_ext.cli.options import (
    option_dev_mode,
    option_group,
    option_output_dir,
    option_output_file,
)
from pkg_ext.cli.workflow_cmds import (
    generate_docs_for_pkg,
    generate_examples_for_groups,
    generate_tests_for_groups,
)
from pkg_ext.cli.workflows import create_api_dump, write_api_dump
from pkg_ext.git_usage import git_show_file
from pkg_ext.models.api_dump import PublicApiDump
from pkg_ext.settings import PkgSettings

logger = logging.getLogger(__name__)


def dump_api(
    ctx: typer.Context,
    output: Path | None = option_output_file,
    dev: bool = option_dev_mode,
):
    """Dump public API to YAML for diffing and breaking change detection."""
    settings: PkgSettings = ctx.obj
    if output is None:
        write_api_dump(settings, dev_mode=dev)
    else:
        api_dump = create_api_dump(settings)
        yaml_text = dump(api_dump.model_dump(exclude_none=True), "yaml")
        ensure_parents_write_text(output, yaml_text)
        logger.info(f"API dump written to {output}")


def gen_examples(
    ctx: typer.Context,
    group: str | None = option_group,
):
    """Generate example files for public API functions."""
    settings: PkgSettings = ctx.obj
    api_dump = create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    generate_examples_for_groups(settings, groups)


def gen_tests(
    ctx: typer.Context,
    group: str | None = option_group,
):
    """Generate parameterized test files from examples."""
    settings: PkgSettings = ctx.obj
    api_dump = create_api_dump(settings)
    groups = [api_dump.get_group(group)] if group else api_dump.groups
    generate_tests_for_groups(settings, groups)


def gen_docs(
    ctx: typer.Context,
    output_dir: Path | None = option_output_dir,
    group: str | None = option_group,
):
    """Generate documentation from public API."""
    settings: PkgSettings = ctx.obj
    count = generate_docs_for_pkg(settings, output_dir=output_dir, filter_group=group)
    docs_dir = output_dir or settings.docs_dir
    logger.info(f"Generated {count} doc files in {docs_dir}")


def diff_api(
    ctx: typer.Context,
    baseline_ref: str | None = typer.Option(
        None,
        "--baseline",
        help="Git tag/ref to compare against (default: {pkg}.api.yaml file)",
    ),
):
    """Show API changes between baseline and dev dump."""
    settings: PkgSettings = ctx.obj
    dev_path = settings.api_dump_dev_path
    baseline_path = settings.api_dump_baseline_path

    write_api_dump(settings, dev_mode=True)
    dev_dump = parse_model(dev_path, t=PublicApiDump)

    # Load baseline
    baseline: PublicApiDump | None = None
    if baseline_ref:
        content = git_show_file(settings.repo_root, baseline_ref, baseline_path)
        if content is None:
            logger.info(f"No baseline found at {baseline_ref}:{baseline_path.name}")
        else:
            baseline = parse_model(content, t=PublicApiDump)
    elif baseline_path.exists():
        baseline = parse_model(baseline_path, t=PublicApiDump)
    else:
        logger.info("No baseline found (first release)")

    results = api_diff.compare_api_dumps(baseline, dev_dump)
    typer.echo(api_diff.format_diff_results(results))
