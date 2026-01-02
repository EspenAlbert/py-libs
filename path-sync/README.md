# path-sync

Sync files from a source repo to multiple destination repos.

## Overview

**Problem**: You have shared config files (linter rules, CI templates, editor settings) that should be consistent across multiple repositories. Manual copying leads to drift.

**Solution**: path-sync provides one-way file syncing with clear ownership:

| Term | Definition |
|------|------------|
| **SRC** | Source repository containing the canonical files |
| **DEST** | Destination repository receiving synced files |
| **Header** | Comment added to synced files marking them as managed |
| **Section** | Marked region within a file for partial syncing |

**Key behaviors**:
- SRC owns synced content; DEST should not edit it
- Files with headers are updated on each sync
- Remove a header to opt-out (file becomes DEST-owned)
- Orphaned files (removed from SRC) are deleted in DEST

## Installation

```bash
# From PyPI
uvx path-sync --help

# Or install in project
uv pip install path-sync
```

## Quick Start

### 1. Bootstrap a source config

```bash
path-sync boot -n myconfig -d ../dest-repo1 -d ../dest-repo2 -p '.cursor/**/*.mdc'
```

Creates `.github/myconfig.src.yaml` with auto-detected git remote and destinations.

### 2. Copy files to destinations

```bash
path-sync copy -n myconfig
```

By default, prompts before each git operation. See [Usage Scenarios](#usage-scenarios) for common patterns.

| Flag | Description |
|------|-------------|
| `-d dest1,dest2` | Filter specific destinations |
| `--dry-run` | Preview without writing (requires existing repos) |
| `-y, --no-prompt` | Skip confirmations (for CI) |
| `--local` | No git ops after sync (no commit/push/PR) |
| `--no-checkout` | Skip branch switching (assumes already on correct branch) |
| `--checkout-from-default` | Reset to origin/default before sync |
| `--no-pr` | Push but skip PR creation |
| `--force-overwrite` | Overwrite files even if header removed (opted out) |
| `--detailed-exit-code` | Exit 0=no changes, 1=changes, 2=error |
| `--skip-orphan-cleanup` | Skip deletion of orphaned synced files |
| `--pr-title` | Override PR title (supports `{name}`, `{dest_name}`) |
| `--pr-labels` | Comma-separated PR labels |
| `--pr-reviewers` | Comma-separated PR reviewers |
| `--pr-assignees` | Comma-separated PR assignees |

### 3. Validate (run in dest repo)

```bash
uvx path-sync validate-no-changes -b main
```

Options:
- `-b, --branch` - Default branch to compare against (default: main)
- `--skip-sections` - Comma-separated `path:section_id` pairs to skip (e.g., `justfile:coverage`)

## Usage Scenarios

| Scenario | Command |
|----------|---------|
| Interactive sync | `copy -n cfg` |
| CI fresh sync | `copy -n cfg --checkout-from-default -y` |
| Local preview | `copy -n cfg --dry-run` |
| Local test files | `copy -n cfg --local` |
| Already on branch | `copy -n cfg --no-checkout` |
| Push, manual PR | `copy -n cfg --no-pr -y` |
| Force opted-out | `copy -n cfg --force-overwrite` |

**Interactive prompt behavior**: Declining the checkout prompt syncs files but skips commit/push/PR (same as `--local`). Use `--no-checkout` when you're already on the correct branch and want to proceed with git operations.

## Section Markers

For partial file syncing (e.g., `justfile`, `pyproject.toml`), wrap sections with markers:

```makefile
# === DO_NOT_EDIT: path-sync default ===
lint:
    ruff check .
# === OK_EDIT ===
```

- **`DO_NOT_EDIT: path-sync {id}`** - Start of managed section with identifier
- **`OK_EDIT`** - End marker (content below is editable)

During sync, only content within markers is replaced. Destination can have extra sections.

Use `skip_sections` in destination config to exclude specific sections from sync:

```yaml
destinations:
  - name: dest1
    dest_path_relative: ../dest1
    skip_sections:
      justfile: [coverage]  # keep local coverage recipe
```
## Config Reference

**Source config** (`.github/{name}.src.yaml`):

```yaml
name: cursor
src_repo_url: https://github.com/user/src-repo
schedule: "0 6 * * *"
paths:
  - src_path: .cursor/**/*.mdc
  - src_path: templates/justfile
    dest_path: justfile
destinations:
  - name: dest1
    repo_url: https://github.com/user/dest1
    dest_path_relative: ../dest1
    # copy_branch: sync/cursor  # defaults to sync/{config_name}
    default_branch: main
    skip_sections:
      justfile: [coverage]
```

| Field | Description |
|-------|-------------|
| `name` | Config identifier |
| `src_repo_url` | Source repo URL (auto-detected from git remote) |
| `schedule` | Cron for scheduled sync workflow |
| `paths` | Files/globs to sync (`src_path` required, `dest_path` optional) |
| `destinations` | Target repos with sync settings |
| `header_config` | Comment style per extension (has defaults) |
| `pr_defaults` | PR title, labels, reviewers, assignees |

## Header Format

Synced files have a header comment identifying the source config:

```python
# path-sync copy -n myconfig
```

Comment style is extension-aware:

| Extension | Format |
|-----------|--------|
| `.py`, `.sh`, `.yaml` | `# path-sync copy -n {name}` |
| `.go`, `.js`, `.ts` | `// path-sync copy -n {name}` |
| `.md`, `.mdc`, `.html` | `<!-- path-sync copy -n {name} -->` |

Remove this header to opt-out of future syncs for that file.

## GitHub Actions

### Source repo workflow

Create `.github/workflows/path_sync_copy.yaml`:

```yaml
name: path-sync copy
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uvx path-sync copy -n myconfig --checkout-from-default -y
        env:
          GH_TOKEN: ${{ secrets.GH_PAT }}
```

### Destination repo validation

Create `.github/workflows/path_sync_validate.yaml`:

```yaml
name: path-sync validate
on:
  push:
    branches-ignore:
      - main
      - sync/**
  pull_request:
    branches:
      - main

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
      - run: uvx path-sync validate-no-changes -b main
```

**Validation skips automatically when:**
- On a `sync/*` branch (path-sync uses `sync/{config_name}` by default)
- On the default branch (comparing against itself)

The workflow triggers exclude these branches too, reducing unnecessary CI runs.

### PAT Requirements

Create a **Fine-grained PAT** at <https://github.com/settings/tokens?type=beta>

| Permission | Scope |
|------------|-------|
| Contents | Read/write (push branches) |
| Pull requests | Read/write (create PRs) |
| Workflows | Read/write (if syncing `.github/workflows/`) |
| Metadata | Read (always required) |

Add as repository secret: `GH_PAT`

### Common Errors

| Error | Fix |
|-------|-----|
| `HTTP 404: Not Found` | Add repo to PAT's repository access |
| `HTTP 403: Resource not accessible` | Add Contents + Pull requests permissions |
| `GraphQL: Resource not accessible` | Use GH_PAT, not GITHUB_TOKEN |
| `HTTP 422: Required status check` | Exclude `sync/*` from branch protection |

## Alternatives Considered

| Tool | Why Not |
|------|---------|
| [repo-file-sync-action](https://github.com/BetaHuhn/repo-file-sync-action) | No local CLI, no validation |
| [Copier](https://copier.readthedocs.io/) | Merge-based (conflicts), no multi-dest |
| [Cruft](https://cruft.github.io/cruft/) | Patch-based, single dest |

**Why path-sync:**
- One SRC to many DEST repos
- Local CLI + CI support
- Section-level sync for shared files
- Validation enforced across repos
- Clear ownership (no merge conflicts)
