import pytest

from path_sync import sections

JUSTFILE_CONTENT = """\
# path-sync copy -n python-template

# === OK_EDIT ===
# Custom variables

# === DO_NOT_EDIT: path-sync standard ===
pre-push: lint test
# === OK_EDIT ===

# === DO_NOT_EDIT: path-sync coverage ===
cov:
  uv run pytest --cov
# === OK_EDIT ===
"""


def test_parse_sections():
    result = sections.parse_sections(JUSTFILE_CONTENT)
    assert len(result) == 2
    assert result[0].id == "standard"
    assert result[0].content == "pre-push: lint test"
    assert result[1].id == "coverage"
    assert "uv run pytest --cov" in result[1].content


def test_parse_sections_no_markers():
    assert sections.parse_sections("just plain content\nno markers") == []


def test_parse_sections_nested_error():
    content = """\
# === DO_NOT_EDIT: path-sync outer ===
# === DO_NOT_EDIT: path-sync inner ===
# === OK_EDIT ===
# === OK_EDIT ===
"""
    with pytest.raises(ValueError, match="Nested section"):
        sections.parse_sections(content)


def test_parse_sections_unclosed_error():
    content = "# === DO_NOT_EDIT: path-sync test ===\nsome content"
    with pytest.raises(ValueError, match="Unclosed section"):
        sections.parse_sections(content)


def test_parse_sections_standalone_ok_edit():
    content = "# === OK_EDIT ===\nsome content\n# === OK_EDIT ==="
    assert (
        sections.parse_sections(content) == []
    )  # standalone OK_EDIT is valid, ignored


def test_has_sections():
    assert sections.has_sections(JUSTFILE_CONTENT)
    assert not sections.has_sections("plain content")


def test_wrap_in_default_section():
    result = sections.wrap_in_default_section("content here")
    assert "DO_NOT_EDIT: path-sync default" in result
    assert "content here" in result
    assert result.endswith("# === OK_EDIT ===")


def test_extract_sections():
    result = sections.extract_sections(JUSTFILE_CONTENT)
    assert result == {
        "standard": "pre-push: lint test",
        "coverage": "cov:\n  uv run pytest --cov",
    }


def test_replace_sections_updates_content():
    dest = """\
# === DO_NOT_EDIT: path-sync standard ===
old content
# === OK_EDIT ==="""
    src_sections = {"standard": "new content"}
    result = sections.replace_sections(dest, src_sections)
    assert "new content" in result
    assert "old content" not in result


def test_replace_sections_preserves_ok_edit():
    dest = """\
# custom header
# === DO_NOT_EDIT: path-sync standard ===
old
# === OK_EDIT ===
# my custom stuff"""
    result = sections.replace_sections(dest, {"standard": "new"})
    assert "# custom header" in result
    assert "# my custom stuff" in result


def test_replace_sections_skip():
    dest = """\
# === DO_NOT_EDIT: path-sync standard ===
keep this
# === OK_EDIT ==="""
    result = sections.replace_sections(
        dest, {"standard": "replaced"}, skip_sections=["standard"]
    )
    assert "keep this" in result  # skipped sections preserve dest content
    assert "replaced" not in result


def test_replace_sections_adds_new():
    dest = "# plain file"
    result = sections.replace_sections(dest, {"newid": "new content"})
    assert "DO_NOT_EDIT: path-sync newid" in result
    assert "new content" in result


def test_replace_sections_keeps_dest_only():
    dest = """\
# === DO_NOT_EDIT: path-sync custom ===
my custom section
# === OK_EDIT ==="""
    result = sections.replace_sections(dest, {})
    assert "my custom section" in result  # dest-only sections preserved
    assert "DO_NOT_EDIT: path-sync custom" in result
