from __future__ import annotations

import logging
from pathlib import Path

from path_sync import git_ops, header, sections

logger = logging.getLogger(__name__)


def parse_skip_sections(value: str) -> dict[str, set[str]]:
    """Parse 'path:section_id,path:section_id' into {path: {section_ids}}."""
    result: dict[str, set[str]] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid format '{item}', expected 'path:section_id'")
        path, section_id = item.rsplit(":", 1)
        result.setdefault(path, set()).add(section_id)
    return result


def compare_sections(
    baseline_content: str,
    current_content: str,
    skip: set[str],
) -> list[str]:
    """Return section IDs with unauthorized changes (modified or removed)."""
    baseline_secs = sections.extract_sections(baseline_content)
    current_secs = sections.extract_sections(current_content)

    changed: list[str] = []
    for sec_id, baseline_text in baseline_secs.items():
        if sec_id in skip:
            continue
        current_text = current_secs.get(sec_id, "")
        if baseline_text != current_text:
            changed.append(sec_id)
    return changed


def validate_no_unauthorized_changes(
    repo_root: Path,
    default_branch: str = "main",
    skip_sections: dict[str, set[str]] | None = None,
) -> list[str]:
    """Find files with unauthorized changes in DO_NOT_EDIT sections.

    Returns 'path:section_id' for section changes or 'path' for full-file.
    """
    repo = git_ops.get_repo(repo_root)
    base_ref = f"origin/{default_branch}"
    skip = skip_sections or {}
    unauthorized: list[str] = []

    for path in git_ops.get_changed_files(repo, base_ref):
        if not path.exists():
            continue
        if not header.file_has_header(path):
            continue

        rel_path = str(path.relative_to(repo_root))
        current_content = path.read_text()
        baseline_content = git_ops.get_file_content_at_ref(repo, path, base_ref)

        if baseline_content is None:
            continue

        baseline_has_sections = sections.has_sections(baseline_content)
        current_has_sections = sections.has_sections(current_content)

        if baseline_has_sections:
            file_skip = skip.get(rel_path, set())
            changed_ids = compare_sections(baseline_content, current_content, file_skip)
            unauthorized.extend(f"{rel_path}:{sid}" for sid in changed_ids)
        elif current_has_sections:
            unauthorized.append(rel_path)
        else:
            if baseline_content != current_content:
                unauthorized.append(rel_path)

    return sorted(unauthorized)
