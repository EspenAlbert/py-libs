from pkg_ext.cov_reader import cov_lines, is_covered


def test_is_covered(coverage_xml_test):
    coverage_path = coverage_xml_test
    full_path = "pkg-ext/pkg_ext/ref_processor.py"
    assert is_covered(coverage_path, full_path, 46)
    assert not is_covered(coverage_path, full_path, 47)


def test_lines(repo_path, coverage_xml_test):
    coverage_path = coverage_xml_test
    full_path = "pkg-ext/pkg_ext/ref_processor.py"
    lines = cov_lines(repo_path, coverage_path, full_path)
    assert lines
    # assert (
    #     lines[46].source == "    def current_state(self, ref_name: str) -> RefState:\n"
    # )
    # assert lines[47].source == "        if state := self.refs.get(ref_name):\n"
