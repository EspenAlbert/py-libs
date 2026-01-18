from datetime import UTC, datetime
from pathlib import Path

from pkg_ext.config import ROOT_GROUP_NAME
from pkg_ext.generation.docs import GeneratedDocsOutput
from pkg_ext.generation.docs_mkdocs import (
    MkdocsSection,
    copy_readme_as_index,
    generate_mkdocs_nav,
    write_docs_files,
    write_mkdocs_yml,
)
from pkg_ext.models.api_dump import GroupDump, PublicApiDump


def test_copy_readme_as_index(tmp_path: Path):
    state_dir = tmp_path / "pkg"
    state_dir.mkdir()
    (state_dir / "readme.md").write_text("# My Package\n\nDescription here.")
    docs_dir = tmp_path / "docs"
    index = copy_readme_as_index(state_dir, docs_dir, "my_pkg")
    assert index.exists()
    assert "# My Package" in index.read_text()


def test_copy_readme_fallback(tmp_path: Path):
    state_dir = tmp_path / "pkg"
    state_dir.mkdir()
    docs_dir = tmp_path / "docs"
    index = copy_readme_as_index(state_dir, docs_dir, "my_pkg")
    assert index.read_text() == "# my_pkg\n"


def test_generate_mkdocs_nav():
    api_dump = PublicApiDump(
        pkg_import_name="my_pkg",
        version="1.0.0",
        dumped_at=datetime.now(UTC),
        groups=[
            GroupDump(name=ROOT_GROUP_NAME, symbols=[]),
            GroupDump(name="config", symbols=[]),
        ],
    )
    nav = generate_mkdocs_nav(api_dump, "my_pkg")
    assert nav[0] == {"Home": "index.md"}
    assert {"my_pkg": "_root/index.md"} in nav
    assert {"config": "config/index.md"} in nav


def test_write_mkdocs_yml_creates_new(tmp_path: Path):
    mkdocs_path = tmp_path / "mkdocs.yml"
    nav = [{"Home": "index.md"}, {"config": "config/index.md"}]
    write_mkdocs_yml(mkdocs_path, "my_pkg", nav)
    content = mkdocs_path.read_text()
    assert "site_name: my_pkg" in content
    assert "nav:" in content
    for section in MkdocsSection:
        assert f"DO_NOT_EDIT: pkg-ext {section.value}" in content


def test_write_mkdocs_yml_honors_skip_sections(tmp_path: Path):
    mkdocs_path = tmp_path / "mkdocs.yml"
    nav = [{"Home": "index.md"}]
    write_mkdocs_yml(mkdocs_path, "my_pkg", nav, skip_sections=("theme", "extensions"))
    content = mkdocs_path.read_text()
    assert "site_name:" in content
    assert "theme:" not in content


def test_write_docs_files_idempotent(tmp_path: Path):
    docs_dir = tmp_path / "docs"
    output = GeneratedDocsOutput(path_contents={"config/index.md": "# Config\n"})
    count1 = write_docs_files(output, docs_dir)
    content1 = (docs_dir / "config/index.md").read_text()
    count2 = write_docs_files(output, docs_dir)
    content2 = (docs_dir / "config/index.md").read_text()
    assert count1 == count2 == 1
    assert content1 == content2
