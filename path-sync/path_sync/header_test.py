from path_sync import header


def test_header_generation():
    assert header.get_header_line(".py", "my-config") == "# path-sync copy -n my-config"
    assert (
        header.get_header_line(".go", "my-config") == "// path-sync copy -n my-config"
    )
    assert (
        header.get_header_line(".md", "my-config")
        == "<!-- path-sync copy -n my-config -->"
    )


def test_has_header_matches_any_config_name():
    assert header.has_header("# path-sync copy -n my-config\ncode", ".py")
    assert header.has_header("# path-sync copy -n other_name\ncode", ".py")
    assert not header.has_header(
        "# DO NOT EDIT: path-sync destination file\ncode", ".py"
    )
    assert not header.has_header("print('hello')", ".py")


def test_add_remove_header():
    content = "print('hello')"
    with_header = header.add_header(content, ".py", "test-config")
    assert header.has_header(with_header, ".py")
    without = header.remove_header(with_header, ".py")
    assert without == content


def test_file_has_header(tmp_path):
    py_file = tmp_path / "test.py"
    py_file.write_text(header.add_header("content", ".py", "my-config"))
    assert header.file_has_header(py_file)

    no_header = tmp_path / "plain.py"
    no_header.write_text("content")
    assert not header.file_has_header(no_header)

    unsupported = tmp_path / "data.whl"
    unsupported.write_bytes(b"\x00\x01\x02\x03")
    assert not header.file_has_header(unsupported)
