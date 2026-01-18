# Pkg Ext

A CLI tool for managing Python package public API, versioning, and changelog generation.

## Overview

`pkg-ext` tracks which symbols (functions, classes, exceptions) in your package are "exposed" (public) vs "hidden" (internal). It:
- Generates `__init__.py` with imports and `__all__` based on decisions stored in changelog entries
- Creates group modules (e.g., `my_group.py`) that re-export related symbols
- Maintains a structured changelog directory (`.changelog/`) per PR
- Bumps version based on changelog action types (make_public=minor, fix=patch, delete/rename=major)
- Writes a human-readable `CHANGELOG.md`
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
| `max_bump_type` | Cap version bump | None | `max_bump`, `reason` |
| `chore` | Internal changes | Patch | `description` |

All actions inherit common fields: `name`, `ts`, `author`, `pr`.

The `breaking_change` and `additional_change` actions support optional fields for API diff:
- `change_kind: str | None` - machine-readable change type (e.g., `param_removed`, `default_changed`)
- `auto_generated: bool` - `true` when created by API diff, `false` for interactive actions
- `field_name: str | None` - field name for field-level changes

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

#### When to Use

| Scenario | Command |
|----------|---------|
| Added or removed symbols | `pre-change` |
| Final validation before commit | `pre-commit` |
| Single command for everything | `pre-change --full` |
| CI/CD pipeline | `pre-commit` (bot mode) |

- **`pre-change`** handles interactive decisions (expose/hide symbols, delete/rename). Fast because it only generates example and test scaffolds.
- **`pre-commit`** validates all decisions are made (fails in bot mode if prompts needed), syncs generated files, regenerates docs, and runs the dirty check.
- **`pre-change --full`** combines both: runs interactive prompts, generates examples/tests, then syncs files and regenerates docs. The dirty check is skipped since you're still developing.

#### `pre-change`

Prompts for new symbols (expose or hide) and removed symbols (delete or alias). Generates `{group}_examples.py` and `{group}_test.py` scaffolds.

```bash
pkg-ext pre-change                     # All groups
pkg-ext pre-change -g config           # Single group
pkg-ext pre-change --full              # Also run pre-commit workflow
pkg-ext pre-change --full --skip-docs  # Skip docs generation
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
pkg-ext post-merge --pr 123 --force-reason "CI improvements"  # Force release
```

When no changelog entries exist for a PR, `post-merge` skips the release (no version bump, no tag). Use `--force-reason` to force a release by auto-creating a `ChoreAction`.

#### `chore`

Create a `ChoreAction` for internal changes that warrant a release but don't affect the public API.

```bash
pkg-ext chore -d "CI improvements"           # Auto-detect PR number
pkg-ext chore -d "Dependency updates" --pr 4 # Explicit PR number
```

Use when merging PRs with internal changes (refactoring, CI updates, dependency bumps) that should trigger a patch release.

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

#### `diff-api`

Compare baseline API dump against current code to detect breaking and non-breaking changes.

```bash
pkg-ext diff-api                    # Compare {pkg}.api.yaml vs current code
pkg-ext diff-api --baseline v1.0.0  # Compare against specific git tag/ref
```

Outputs a summary grouped by breaking and non-breaking changes. The comparison runs automatically during `pre-commit`; this command is for manual inspection.

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
max_bump_type = "minor"  # Cap version bumps (patch, minor, major)
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

## API Diff and Breaking Change Detection

During `pre-commit`, pkg-ext compares `{pkg}.api.yaml` (baseline from last release) against `{pkg}.api-dev.yaml` (current code) to detect API changes.

### Detected Change Types

| Change | Breaking? | `change_kind` |
|--------|-----------|---------------|
| Parameter removed | Yes | `param_removed` |
| Required parameter added | Yes | `required_param_added` |
| Parameter type changed | Yes | `param_type_changed` |
| Return type changed | Yes | `return_type_changed` |
| Default removed | Yes | `default_removed` |
| Required field added | Yes | `required_field_added` |
| Field removed | Yes | `field_removed` |
| Base class removed | Yes | `base_class_removed` |
| Optional parameter added | No | `optional_param_added` |
| Default added | No | `default_added` |
| Default changed | No | `default_changed` |
| Optional field added | No | `optional_field_added` |

### Auto-Generated Actions

API diff creates `BreakingChangeAction` or `AdditionalChangeAction` entries with `auto_generated: true`. These are:
- Replaced on each `pre-commit` run
- Keyed by `(name, group, type, change_kind)` for deduplication
- Timestamps preserved for unchanged changes

Interactive actions (from `pre-change`) are never replaced.

### First Release

When no baseline `{pkg}.api.yaml` exists, diff is skipped (nothing to compare against).

## Version Bump Override

For pre-1.0.0 packages where breaking changes are expected, cap the version bump using project config:

```toml
# pyproject.toml
[tool.pkg-ext]
max_bump_type = "minor"  # All PRs capped to minor
```

For per-PR overrides, use `MaxBumpTypeAction` in the changelog (overrides config):

```yaml
# .changelog/{pr}.yaml
name: version_cap
type: max_bump_type
max_bump: patch
reason: Documentation-only release
ts: '2026-01-17T14:35:00+00:00'
```

Precedence: `MaxBumpTypeAction` overrides `max_bump_type` config (allows per-PR escape from project default).

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

### API Diff
- **No rename detection** - Renames are treated as remove + add (two separate actions)
- **Return types always breaking** - No semantic analysis (e.g., returning subclass is flagged as breaking)
- **Factory defaults** - Defaults using `"..."` (factory pattern) may cause false positives

## File Structure

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
