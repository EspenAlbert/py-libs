"""Generation commands: gen_examples, gen_tests, gen_docs, dump_api."""

import logging
from pathlib import Path

import typer
from model_lib.serialize import dump
from zero_3rdparty.file_utils import ensure_parents_write_text

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
