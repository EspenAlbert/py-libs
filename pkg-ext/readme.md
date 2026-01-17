# Pkg Ext

A CLI tool for managing Python package public API, versioning, and changelog generation.

## Overview

`pkg-ext` tracks which symbols (functions, classes, exceptions) in your package are "exposed" (public) vs "hidden" (internal). It:
- Generates `__init__.py` with imports and `__all__` based on decisions stored in changelog entries
- Creates group modules (e.g., `my_group.py`) that re-export related symbols
- Maintains a structured changelog directory (`.changelog/`) per PR
- Bumps version based on changelog action types (make_public=minor, fix=patch, delete/rename=major)
- Writes a human-readable `CHANGELOG.md`
- Supports flat packages (all modules public) with automatic changelog tracking
- Provides [stability decorators](docs/stability.md) (`@experimental`, `@deprecated`) with suppressible warnings
- Generates `_warnings.py` in target packages to avoid runtime pkg-ext dependency

## Installation

```bash
uv pip install pkg-ext
# or
pip install pkg-ext
```

## Core Concepts

### Symbol Reference IDs
Symbols are identified by `{module_path}.{symbol_name}`, e.g., `my_pkg.utils.parse_config`.

### Changelog Actions
Stored in `.changelog/{pr_number}.yaml` files using Pydantic discriminated unions:

| Action Type | Description | Version Bump | Key Fields |
|-------------|-------------|--------------|------------|
| `make_public` | Make symbol public | Minor | `group`, `details` |
| `keep_private` | Keep symbol internal | None | `full_path` |
| `fix` | Bug fix from git commit | Patch | `short_sha`, `message`, `changelog_message`, `ignored` |
| `delete` | Remove from public API | Major | `group` |
| `rename` | Rename with old alias | Major | `group`, `old_name` |
| `breaking_change` | Breaking API change | Major | `group`, `details` |
| `additional_change` | Non-breaking change | Patch | `group`, `details` |
| `group_module` | Assign module to a group | None | `module_path` |
| `release` | Version release marker | None | `old_version` |
| `experimental` | Mark as experimental | Patch | `target`, `group`/`parent` |
| `ga` | Graduate to GA | Patch | `target`, `group`/`parent` |
| `deprecated` | Mark as deprecated | Patch | `target`, `group`/`parent`, `replacement` |

All actions inherit common fields: `name`, `ts`, `author`, `pr`.

### Stability Targets

Stability actions (`experimental`, `ga`, `deprecated`) support three target levels:

| Target | Description | Required Field |
|--------|-------------|----------------|
| `group` | Entire group | `name` = group name |
| `symbol` | Single symbol | `group` + `name` = symbol name |
| `arg` | Function argument | `parent` = `{group}.{symbol}`, `name` = arg name |

### Public Groups
Groups organize related symbols. Configured in `.groups.yaml`:

```yaml
groups:
  - name: __ROOT__  # Top-level exports in __init__.py
    owned_refs: []
    owned_modules: []
  - name: my_group
    owned_refs:
      - my_pkg.utils.parse_config
    owned_modules:
      - my_pkg.utils
```

When a new symbol is exposed, the tool prompts you to select which group it belongs to. All symbols from the same module go to the same group.

### Flat Packages

Packages can opt into "flat mode" via configuration. Flat packages have modules at the root level instead of using a `_internal/` subdirectory structure.

Enable in `pyproject.toml`:

```toml
[tool.pkg-ext]
flat_package = true
```

**Current flat package behavior:**

| Aspect | Standard Package | Flat Package (current) |
|--------|------------------|------------------------|
| Added refs | Prompt: expose/hide + group selection | Auto-expose, module name = group |
| Removed refs | Prompt: rename/delete confirmation | Auto-delete |
| `__init__.py` | Group imports + VERSION + `__all__` | VERSION only (no imports) |
| Group modules | Generated (e.g., `my_group.py`) | Not generated |
| Fix commits | Prompt: include/exclude + group selection | Prompt: include/exclude, auto-infer group |
| Stability | Group/symbol/arg levels | Same (tracked in changelog) |

**Planned change:** Flat packages will use the same interactive prompts as standard packages in a future release. The only difference will be import paths (no `_internal/` prefix) and default group suggestion (module name).

**When to use flat packages:**
- Libraries where users import directly from modules (e.g., `from pkg.utils import func`)
- Simple packages without `_internal` private modules
- Packages where all public modules are part of the public API

**Example flat package structure:**

```
zero_3rdparty/
  __init__.py       # VERSION only (current), will include imports in future
  file_utils.py     # group: file_utils
  iter_utils.py     # group: iter_utils
  datetime_utils.py # group: datetime_utils
```

**Generated `.groups.yaml`:**

```yaml
groups:
  - name: __ROOT__
  - name: file_utils
    owned_modules: [file_utils]
    owned_refs: [file_utils.read_file, file_utils.write_file]
  - name: iter_utils
    owned_modules: [iter_utils]
    owned_refs: [iter_utils.flat_map, iter_utils.first]
```

Users import directly from modules: `from zero_3rdparty.file_utils import read_file`.

## CLI Commands

```bash
pkg-ext [OPTIONS] COMMAND
```

### Global Options

| Option | Description |
|--------|-------------|
| `-p, --path, --pkg-path` | Package directory path (auto-detected if not provided) |
| `--repo-root` | Repository root (auto-detected from `.git`) |
| `--is-bot` | CI mode: no prompts, fail on missing decisions |
| `--skip-open` | Skip opening files in editor |
| `--tag-prefix` | Git tag prefix (e.g., `v` for `v1.0.0`) |

### Workflow Commands

| Command | When | Interactive | Writes |
|---------|------|-------------|--------|
| `pre-change` | After adding/removing symbols | Yes | Examples, tests |
| `pre-commit` | Before commit / CI validation | No | `-dev` files, docs |
| `post-merge` | After merge to main | No | Real files, tag |

#### `pre-change`

Prompts for new symbols (expose or hide) and removed symbols (delete or alias). Generates `{group}_examples.py` and `{group}_test.py` scaffolds.

```bash
pkg-ext pre-change           # All groups
pkg-ext pre-change -g config # Single group
```

#### `pre-commit`

Runs in bot mode (fails if pending prompts). Updates `.groups-dev.yaml`, `CHANGELOG-dev.md`, and docs.

```bash
pkg-ext pre-commit              # With docs
pkg-ext pre-commit --skip-docs  # Skip docs for faster iteration
```

#### `post-merge`

Run after merge on default branch. Bumps version, creates git tag, cleans old changelog entries.

```bash
pkg-ext post-merge --push --pr 123
```

### Stability Commands

Manage stability at group, symbol, and argument levels. All stability state is tracked in `.changelog/` as the single source of truth.

**Target format:** `{group}` or `{group}.{symbol}` or `{group}.{symbol}.{arg}`

**Constraints:**
- Arg-level stability changes require the parent group to be GA
- Commands validate that the target exists before creating an action

#### `exp` - Mark as experimental

```bash
pkg-ext exp --target config              # Mark entire group
pkg-ext exp --target config.parse        # Mark symbol in group
pkg-ext exp --target config.parse.timeout  # Mark argument on symbol
```

#### `ga` - Graduate to GA

```bash
pkg-ext ga --target config               # Graduate group to stable
pkg-ext ga --target config.parse         # Graduate symbol
```

#### `dep` - Mark as deprecated

```bash
pkg-ext dep --target config --replacement new_config
pkg-ext dep --target config.parse.callback --replacement on_done
```

### Utility Commands

#### `dump-groups`

Regenerate `.groups.yaml` with merged config data (for debugging group assignments).

```bash
pkg-ext dump-groups
```

#### `release-notes`

Extract changelog section for a specific tag.

```bash
pkg-ext release-notes --tag v1.2.0
```

## Configuration

### User Config (`~/.config/pkg-ext/config.toml`)

```toml
[user]
editor = "cursor"  # or "code", "vim", etc.
skip_open_in_editor = false
```

### Project Config (`pyproject.toml`)

```toml
[tool.pkg-ext]
tag_prefix = "v"
file_header = "# Generated by pkg-ext"
commit_fix_prefixes = ["fix:", "bugfix:", "hotfix:"]
commit_diff_suffixes = [".py", ".pyi"]
changelog_cleanup_count = 30  # Archive when count exceeds this
changelog_keep_count = 10     # Keep this many after cleanup
format_command = ["ruff", "format"]  # ruff check --fix always runs first
# after_file_write_hooks = ["extra-cmd {pkg_path}"]  # Custom post-write hooks
```

### Group Configuration

Define groups with explicit settings in `pyproject.toml`:

```toml
[tool.pkg-ext.groups.my_group]
dependencies = ["__ROOT__"]  # Groups this depends on
docs_exclude = ["internal_helper"]
docstring = "Utilities for common operations"
```

**Note:** Stability is not configured here. Use `pkg-ext exp/ga/dep` CLI commands to manage stability via changelog actions.

### Dev Mode

The `pre-commit` command enables dev mode, which writes to `-dev` suffixed files:
- `.groups-dev.yaml` instead of `.groups.yaml`
- `CHANGELOG-dev.md` instead of `CHANGELOG.md`

This allows iterating on changelog entries during development without modifying the production files. The real files are only updated by `post-merge` after PR is merged.

## Generated Files

### Files Updated During PR

These files are created/updated when running `pre-commit` during development:

| File | Purpose | Editable |
|------|---------|----------|
| `.changelog/{pr}.yaml` | Changelog actions for this PR | Yes |
| `.groups-dev.yaml` | Group assignments (dev copy) | No |
| `CHANGELOG-dev.md` | Human-readable changelog (dev copy) | No |
| `{pkg}.api-dev.yaml` | API dump for dev comparison (gitignored) | No |
| `{pkg}/__init__.py` | Package exports (VERSION unchanged) | No |
| `{pkg}/{group}.py` | Group re-export modules | No |
| `{pkg}/_warnings.py` | Stability warning decorators | No |
| `docs/**/*.md` | API documentation | Yes (outside markers) |
| `{group}_examples.py` | Example scaffolds | Yes (outside markers) |
| `{group}_test.py` | Test scaffolds | Yes (outside markers) |

- `__init__.py` exports are updated but VERSION remains unchanged until release
- Symbol doc pages include a "Changes" table showing unreleased modifications
- Content outside `=== OK_EDIT: pkg-ext ... ===` markers can be customized and is preserved

### Files Updated During Release (main branch only)

These files are updated by `post-merge` after PR is merged:

| File | What Changes |
|------|--------------|
| `.groups.yaml` | Copied from `.groups-dev.yaml` |
| `CHANGELOG.md` | Copied from `CHANGELOG-dev.md` |
| `{pkg}/__init__.py` | VERSION updated to new version |
| `pyproject.toml` | Version field updated (if used) |
| `{pkg}.api.yaml` | Regenerated with new version |
| `docs/**/*.md` | Unreleased changes become versioned |

### File Contents

#### `__init__.py`

**Standard packages:**

```python
# Generated by pkg-ext
# flake8: noqa
from my_pkg import my_group
from my_pkg.utils import parse_config

VERSION = "0.1.0"
__all__ = [
    "my_group",
    "parse_config",
]
```

**Flat packages:**

```python
# Generated by pkg-ext
# flake8: noqa

VERSION = "0.1.0"
```

### Group Module (`my_group.py`)

**Standard (GA stability):**

```python
# Generated by pkg-ext
from my_pkg.helpers import helper_func as _helper_func

helper_func = _helper_func
```

**With experimental stability:**

```python
# Generated by pkg-ext
from my_pkg.helpers import helper_func as _helper_func
from my_pkg._warnings import _experimental

helper_func = _experimental(_helper_func)
```

The underscore alias pattern prevents re-export issues with `__all__`.

### `_warnings.py` (Generated)

When any group has non-GA stability, pkg-ext generates a `_warnings.py` module in the target package. This removes the runtime dependency on pkg-ext.

```python
"""Warning classes and decorators for MyPkg stability levels.

Auto-generated by pkg-ext. Do not edit manually.
"""
# ... implementation details ...

class MyPkgWarning(UserWarning): ...
class MyPkgExperimentalWarning(MyPkgWarning): ...
class MyPkgDeprecationWarning(MyPkgWarning, DeprecationWarning): ...
```

The warning class names use PascalCase of the package name (e.g., `PkgExtWarning` for `pkg_ext`).

### `.changelog/{pr}.yaml`

```yaml
name: parse_config
type: make_public
group: my_group
ts: '2025-01-02T10:00:00+00:00'
author: username
details: created in my_pkg/utils.py
---
name: my_group
type: group_module
ts: '2025-01-02T10:00:01+00:00'
module_path: my_pkg.utils
---
name: my_group
type: experimental
target: group
ts: '2025-01-02T10:00:02+00:00'
```

### `CHANGELOG.md`

```markdown
# Changelog

## 0.1.0 2025-01-02

### My_Group
- New function parse_config

### Other Changes
- Fixed parsing edge case [abc123](https://github.com/user/repo/commit/abc123)
```

## Developer Workflow

### Development Cycle

1. Create branch, make code changes
2. Run `pkg-ext pre-change` - prompts for new/removed symbols, generates scaffolds
3. Fill in examples, run tests locally
4. Run `pkg-ext pre-commit` - validates decisions, updates `-dev` files and docs
5. Commit and push
6. CI runs `pkg-ext pre-commit` - validates all decisions, regenerates docs
7. After merge, CI runs `pkg-ext post-merge` - bumps version, writes real files, creates tag

### Stability Workflow

1. Mark new group as experimental: `pkg-ext exp --target new_group`
2. Develop features, symbols auto-inherit group stability
3. Graduate to GA: `pkg-ext ga --target new_group`
4. Mark arg for deprecation: `pkg-ext dep --target group.func.old_arg --replacement new_arg`

### Git Hook Setup

**Manual hook** (`.git/hooks/pre-commit`):

```bash
#!/bin/bash
pkg-ext pre-commit
```

**[pre-commit](https://pre-commit.com/) framework** (`.pre-commit-config.yaml`):

```yaml
repos:
  - repo: local
    hooks:
      - id: pkg-ext
        name: pkg-ext pre-commit
        entry: pkg-ext pre-commit
        language: system
        pass_filenames: false
```

## Symbol Detection

The tool parses Python files using AST to find:
- **Functions** - Public functions (not starting with `_`)
- **Classes** - Public classes
- **Exceptions** - Classes inheriting from `Exception` or `BaseException`
- **Type Aliases** - Names ending with `T`
- **Global Variables** - UPPERCASE names with 2+ characters

Files skipped:
- `__init__.py`, `__main__.py` (dunder files)
- `*_test.py`, `test_*.py`, `conftest.py` (test files)
- Files starting with the configured `file_header` (already generated)

## Automatic Behaviors

### Function Argument Exposure
When exposing a function, its type hint arguments are auto-exposed if they reference local package types.

### Git Integration
- Uses [GitPython](https://gitpython.readthedocs.io/) for commit analysis
- Uses [gh CLI](https://cli.github.com/) to detect PR info
- Extracts PR number from merge commit message (`Merge pull request #123`)

## Limitations

### Symbol Detection
- **Type aliases require `T` suffix** - e.g., `ConfigT` not `Config`
- **Global vars require UPPERCASE** - e.g., `DEFAULT_TIMEOUT` not `default_timeout`
- **Exceptions require `Error` suffix** - e.g., `ParseError` not `ParseException`
- **No relative import support** - Only `from pkg.module import ...` is tracked

### Group Handling
- **One group per module** - All symbols from a module belong to the same group
- **Cannot move symbols between groups** - Once assigned, module-to-group mapping is fixed
- **Root group always exists** - Cannot be removed, used for top-level exports

### Flat Package Mode
- **Explicit opt-in required** - Set `flat_package = true` in pyproject.toml
- **All public symbols tracked** - Every non-underscore function/class is auto-exposed
- **No interactive prompts** - All decisions are automatic

### Git Requirements
- **Requires `gh` CLI** for PR info detection
- **Merge commit format expected** - `Merge pull request #123 from ...`
- **Single remote assumed** - Uses first remote for URL

### Changelog
- **PR-based storage** - Each PR gets one `.yaml` file
- **No conflict resolution** - Manual merge of `.changelog/` files needed
- **Archiving by PR number** - Old entries archived to `.changelog/000/*.yaml`

### Version Bumping
- **SemVer only** - No calendar versioning support
- **`pyproject.toml` or `__init__.py`** - Version must exist in one of these
- **Pre-release suffixes** - Supports `rc`, `a` (alpha), `b` (beta)

### Interactive Mode
- **Removed reference handling incomplete** - `select_ref` and `select_multiple_ref_state` raise `NotImplementedError`. This breaks rename workflows when symbols are removed.
- **Alias creation not implemented** - `confirm_create_alias` always returns `False`

### Stability
- **Non-callable symbols** - Constants and type aliases in experimental/deprecated groups don't emit warnings. `@experimental` and `@deprecated` only work on functions and classes.
- **Arg-level only for GA groups** - Cannot track arg-level stability changes until group is GA.

## File Structure

**Standard package (with `_internal`):**

```
my-repo/
  CHANGELOG.md           # Human-readable changelog
  .groups.yaml           # Group definitions
  .changelog/            # Per-PR changelog actions
    123.yaml             # Actions from PR #123
    000/                 # Archived old entries
      001.yaml
  my_pkg/
    __init__.py          # Generated exports
    my_group.py          # Generated group module
    _warnings.py         # Generated stability module (if needed)
    utils.py             # Source file
    _internal.py         # Private module (ignored)
```

**Flat package (`flat_package = true`):**

```
my-repo/
  pyproject.toml         # Contains [tool.pkg-ext] flat_package = true
  CHANGELOG.md
  .groups.yaml
  .changelog/
    123.yaml
  my_pkg/
    __init__.py          # VERSION only
    file_utils.py        # All modules public
    iter_utils.py
```

## Dependencies

- **[ask-shell](https://github.com/EspenAlbert/py-libs)** - Interactive prompts and shell execution
- **[model-lib](https://github.com/EspenAlbert/py-libs)** - YAML/TOML parsing and Pydantic models
- **[GitPython](https://gitpython.readthedocs.io/)** - Git repository access

## Appendix: CI Configuration

### GitHub Actions

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pkg-ext
      - run: pkg-ext pre-commit

  release:
    if: github.ref == 'refs/heads/main'
    needs: validate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: pip install pkg-ext
      - run: pkg-ext post-merge --push
```
