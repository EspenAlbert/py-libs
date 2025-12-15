from path_sync import header


def test_header_generation():
    assert header.get_header_line(".py") == "# DO NOT EDIT: path-sync destination file"
    assert header.get_header_line(".go") == "// DO NOT EDIT: path-sync destination file"
    assert (
        header.get_header_line(".md")
        == "<!-- DO NOT EDIT: path-sync destination file -->"
    )


def test_has_header():
    py_content = "# DO NOT EDIT: path-sync destination file\nprint('hello')"
    assert header.has_header(py_content, ".py")
    assert not header.has_header("print('hello')", ".py")


def test_add_remove_header():
    content = "print('hello')"
    with_header = header.add_header(content, ".py")
    assert header.has_header(with_header, ".py")
    without = header.remove_header(with_header, ".py")
    assert without == content


def test_file_has_header(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text(header.add_header("content", ".py"))
    assert header.file_has_header(py_file)

    md_file = tmp_path / "readme.md"
    md_file.write_text(header.add_header("# Title", ".md"))
    assert header.file_has_header(md_file)

    no_header = tmp_path / "plain.py"
    no_header.write_text("content")
    assert not header.file_has_header(no_header)

    assert not header.file_has_header(tmp_path / "missing.py")

    unsupported = tmp_path / "data.whl"
    unsupported.write_bytes(b"\x00\x01\x02\x03")
    assert not header.file_has_header(unsupported)
