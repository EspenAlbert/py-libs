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
