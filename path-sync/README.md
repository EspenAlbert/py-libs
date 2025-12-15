# path-sync

Sync files from a source repo to multiple destination repos.

## Installation

```bash
uv pip install -e path-sync/
```

## Quick Start

### 1. Bootstrap a source config

```bash
# From your source repo root
path-sync boot -n myconfig -d ../dest-repo1 -d ../dest-repo2 -p '.cursor/**/*.mdc'
```

Creates `.github/myconfig.src.yaml` with:
- Auto-detected `src_repo_url` from git remote
- Destinations with names extracted from paths
- Always paths from `-p` patterns

### 2. Copy files to destinations

```bash
path-sync copy -n myconfig
```

Options:
- `-d lz,help` - filter specific destinations
- `--dry-run` - preview without changes
- `--validate-first` - run validation before copying
- `--skip-dest-checkout` - use current branch in dest
- `--force-ignore-sha-match` - re-copy even if SHA unchanged
- `--force-no-header-updates` - overwrite files even if header removed (opted out)
- `--no-pr` - skip PR creation

### 3. Validate no unauthorized changes (run in dest repo)

```bash
# If path-sync is installed
path-sync validate-no-changes -n myconfig

# Or using the copied wheel (no installation needed)
uv run --with .github/path_sync-*.whl path-sync validate-no-changes -n myconfig
```

### 4. Clean orphaned synced files (run in dest repo)

```bash
path-sync clean
```

## Config Structure

**Source config** (`.github/{name}.src.yaml`):
```yaml
type: SRC
name: cursor
src_repo_url: https://github.com/user/src-repo
schedule: "0 6 * * *"
always_paths:
  - src_path: .cursor/**/*.mdc
scaffold_paths:
  - src_path: templates/README.md
destinations:
  - name: dest1
    repo_url: https://github.com/user/dest1
    dest_path_relative: ../dest1
    copy_branch: sync/path-sync
    default_branch: main
    tools_update:
      justfile: true           # Add validate recipe to justfile
      path_sync_wheel: true    # Copy path-sync wheel to .github/
      github_workflows: true   # Generate validation workflow
```

## Opt-out Mechanism

Synced files have a header comment (e.g., `<!-- DO NOT EDIT: path-sync destination file -->`).
Remove this header to opt-out of future syncs for that file.

## Header Configuration

The header text and comment styles are configurable in `header_config`:

```yaml
header_config:
  header_text: "DO NOT EDIT: path-sync destination file"  # customize message
  comment_prefixes:    # extension -> prefix mapping
    .py: "#"
    .md: "<!--"
  comment_suffixes:    # optional closing (for HTML-style comments)
    .md: " -->"
```

**Behavior:**
- **Defaults included**: Running `boot` generates config with all supported extensions pre-configured
- **Inherited by DEST**: The `header_config` from SRC is copied to DEST config during `copy`
- **Only configured extensions synced**: Files with extensions not in `comment_prefixes` are skipped
- **Validation uses DEST config**: The `validate-no-changes` and `clean` commands read header config from the dest config

**Supported extensions (defaults):**

| Extension | Prefix | Suffix |
|-----------|--------|--------|
| `.py`, `.sh`, `.yaml`, `.yml` | `#` | |
| `.go`, `.js`, `.ts` | `//` | |
| `.md`, `.mdc`, `.html` | `<!--` | `-->` |

## GitHub Actions

**Source repo**: Set `src_tools_update.github_workflows: true` and run `boot --regen` to generate:
- `.github/workflows/path_sync_{name}_copy.yaml` - scheduled sync workflow

**Destination repos**: Set `tools_update.github_workflows: true` per destination to auto-generate:
- `.github/workflows/path_sync_{name}_validate.yaml` - validation on push (uses the copied wheel)

### PAT Requirements

Create a **Fine-grained Personal Access Token** at <https://github.com/settings/tokens?type=beta>

**Repository access**: Select each destination repository

**Permissions required per destination repo**:
- **Contents**: Read and write (push branches)
- **Pull requests**: Read and write (create PRs)
- **Workflows**: Read and write (required if syncing workflow files to `.github/workflows/`)
- **Metadata**: Read (always required)

**Classic PAT alternative**: Use `repo` + `workflow` scopes

### Setup

1. Create the PAT with permissions above
2. Add as repository secret: Settings > Secrets > Actions > `GH_PAT`
3. The workflow uses `GH_TOKEN: ${{ secrets.GH_PAT }}` for `gh` CLI auth

### Verify Access

```bash
# Test from any machine with gh CLI
export GH_TOKEN=your_pat
gh api repos/owner/dest-repo
gh pr list --repo owner/dest-repo
```

### Branch Protection

The `copy_branch` (default: `sync/path-sync`) is where path-sync pushes changes. This branch typically doesn't need protection rules.

**Potential issues**:
- If wildcard branch protection (e.g., `*`) blocks pushes, exclude `sync/*` pattern
- Required status checks on the PR target branch may delay merge

**Workarounds**:
- Add `sync/path-sync` to branch protection bypass list
- Or use a bot/machine user account with bypass permissions
- The `--no-pr` flag skips PR creation if you prefer manual work

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `HTTP 404: Not Found` | PAT lacks repo access | Add repo to PAT's repository access |
| `HTTP 403: Resource not accessible` | Missing permission | Add Contents + Pull requests permissions |
| `GraphQL: Resource not accessible by integration` | Using GITHUB_TOKEN | Use GH_PAT secret instead |
| `HTTP 422: Required status check` | Branch protection rules | Bypass or exclude `sync/*` branches |

## Alternatives Considered

| Tool | Description | Why Not |
|------|-------------|---------|
| [repo-file-sync-action](https://github.com/BetaHuhn/repo-file-sync-action) | GitHub Action for file sync | No local CLI, no validation workflow, no justfile support |
| [Copier](https://copier.readthedocs.io/) | Template-based project generation | Merge-based (both SRC and DEST can edit), no multi-dest, no validation |
| [Cruft](https://cruft.github.io/cruft/) | Cookiecutter with updates | Patch-based merging, single dest, no CI validation |

**Why path-sync:**
- One SRC to multiple DEST repos (not 1:1)
- Local CLI support (not GitHub Action only)
- Justfile integration for dev workflow
- Validation checks enforced across many repos
- Clear ownership: SRC or DEST, never both (no merge conflicts)
