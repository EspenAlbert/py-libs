from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

from path_sync.models import SrcConfig

logger = logging.getLogger(__name__)

COPY_WORKFLOW_TEMPLATE = """name: "Path Sync: {name} copy"

on:
  workflow_dispatch:
    inputs:
      dest:
        description: "Filter destinations (comma-separated)"
        required: false
        default: ""
      extra_args:
        description: "Extra args for path-sync copy"
        required: false
        default: ""
  schedule:
    - cron: "{schedule}"

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Run path-sync copy
        env:
          GH_TOKEN: ${{{{ secrets.GH_PAT }}}}
        run: |
          ARGS="-n {name}"
          if [ -n "${{{{ inputs.dest }}}}" ]; then
            ARGS="$ARGS -d ${{{{ inputs.dest }}}}"
          fi
          if [ -n "${{{{ inputs.extra_args }}}}" ]; then
            ARGS="$ARGS ${{{{ inputs.extra_args }}}}"
          fi
          uv run path-sync copy $ARGS
"""

WHEEL_GLOB = ".github/path_sync-*.whl"

VALIDATE_WORKFLOW_TEMPLATE = """name: "Path Sync: {name} validate"

on:
  push:
    branches-ignore:
      - "{copy_branch}"
      - "{default_branch}"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Validate no unauthorized changes
        run: uv run --with {wheel_glob} path-sync validate-no-changes -n {name}
"""


def generate_copy_workflow(config: SrcConfig) -> str:
    return COPY_WORKFLOW_TEMPLATE.format(name=config.name, schedule=config.schedule)


def generate_validate_workflow(name: str, copy_branch: str, default_branch: str) -> str:
    return VALIDATE_WORKFLOW_TEMPLATE.format(
        name=name,
        copy_branch=copy_branch,
        default_branch=default_branch,
        wheel_glob=WHEEL_GLOB,
    )


def copy_workflow_path(name: str) -> str:
    return f".github/workflows/path_sync_{name}_copy.yaml"


def validate_workflow_path(name: str) -> str:
    return f".github/workflows/path_sync_{name}_validate.yaml"


class JustfileRecipeKind(StrEnum):
    COPY = "copy"
    VALIDATE = "validate"

    def recipe_name(self, config_name: str) -> str:
        if self == JustfileRecipeKind.COPY:
            return f"path-sync-{config_name}"
        return f"path-sync-validate-{config_name}"

    def generate_recipe(self, config_name: str) -> str:
        recipe_name = self.recipe_name(config_name)
        if self == JustfileRecipeKind.COPY:
            return f"\n# path-sync: copy files to destinations\n{recipe_name}:\n    uv run path-sync copy -n {config_name}\n"
        return f"\n# path-sync: validate no unauthorized changes\n{recipe_name}:\n    uv run --with {WHEEL_GLOB} path-sync validate-no-changes -n {config_name}\n"


def update_justfile(
    justfile_path: Path,
    config_name: str,
    kind: JustfileRecipeKind,
    dry_run: bool,
) -> bool:
    """Update justfile with recipe. Returns True if changes were made."""
    recipe = kind.generate_recipe(config_name)
    recipe_marker = f"{kind.recipe_name(config_name)}:"

    if justfile_path.exists():
        existing = justfile_path.read_text()
        if recipe_marker in existing:
            logger.info(f"Justfile recipe already exists: {recipe_marker}")
            return False
        new_content = existing.rstrip() + recipe
    else:
        new_content = recipe.lstrip()

    if dry_run:
        logger.info(f"[DRY RUN] Would update justfile with recipe: {recipe_marker}")
        return True

    justfile_path.write_text(new_content)
    logger.info(f"Added justfile recipe: {recipe_marker}")
    return True
