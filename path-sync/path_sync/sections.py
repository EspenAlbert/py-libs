from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_START_PATTERN = re.compile(
    r"^#\s*===\s*DO_NOT_EDIT:\s*path-sync\s+(?P<id>\w+)\s*===$", re.MULTILINE
)
SECTION_END_PATTERN = re.compile(r"^#\s*===\s*OK_EDIT\s*===$", re.MULTILINE)


@dataclass
class Section:
    id: str
    content: str
    start_line: int
    end_line: int


def has_sections(content: str) -> bool:
    return bool(SECTION_START_PATTERN.search(content))


def parse_sections(content: str) -> list[Section]:
    lines = content.split("\n")
    sections: list[Section] = []
    current_id: str | None = None
    current_start: int = -1
    content_lines: list[str] = []

    for i, line in enumerate(lines):
        if start_match := SECTION_START_PATTERN.match(line):
            if current_id is not None:
                raise ValueError(
                    f"Nested section at line {i}: found '{start_match.group('id')}' inside '{current_id}'"
                )
            current_id = start_match.group("id")
            current_start = i
            content_lines = []
        elif SECTION_END_PATTERN.match(line):
            if current_id is None:
                continue  # standalone OK_EDIT marks editable region, not an error
            sections.append(
                Section(
                    id=current_id,
                    content="\n".join(content_lines),
                    start_line=current_start,
                    end_line=i,
                )
            )
            current_id = None
            current_start = -1
            content_lines = []
        elif current_id is not None:
            content_lines.append(line)

    if current_id is not None:
        raise ValueError(
            f"Unclosed section '{current_id}' starting at line {current_start}"
        )

    return sections


def wrap_in_default_section(content: str) -> str:
    return f"# === DO_NOT_EDIT: path-sync default ===\n{content}\n# === OK_EDIT ==="


def extract_sections(content: str) -> dict[str, str]:
    return {s.id: s.content for s in parse_sections(content)}


def replace_sections(
    dest_content: str,
    src_sections: dict[str, str],
    skip_sections: list[str] | None = None,
) -> str:
    skip = set(skip_sections or [])
    dest_parsed = parse_sections(dest_content)
    dest_ids = {s.id for s in dest_parsed}
    dest_sections = {s.id: s.content for s in dest_parsed}
    lines = dest_content.split("\n")
    result: list[str] = []

    current_section_id: str | None = None
    for line in lines:
        if start_match := SECTION_START_PATTERN.match(line):
            current_section_id = start_match.group("id")
            result.append(line)
        elif SECTION_END_PATTERN.match(line):
            if current_section_id:
                should_replace = (
                    current_section_id in src_sections
                    and current_section_id not in skip
                )
                content = (
                    src_sections[current_section_id]
                    if should_replace
                    else dest_sections.get(current_section_id, "")
                )
                if content:
                    result.append(content)
            result.append(line)
            current_section_id = None
        elif current_section_id is None:
            result.append(line)

    # Append new sections from source not in dest
    for sid in src_sections:
        if sid not in dest_ids and sid not in skip:
            result.append(f"# === DO_NOT_EDIT: path-sync {sid} ===")
            result.append(src_sections[sid])
            result.append("# === OK_EDIT ===")

    return "\n".join(result)
