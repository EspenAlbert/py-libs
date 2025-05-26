from ask_shell import BashConfig


def test_infer_print_prefix():
    config = BashConfig(script="terraform apply")
    assert config.print_prefix == "terraform apply"


def test_infer_print_prefix_with_cwd(tmp_path):
    cwd = tmp_path / "tf_module"
    config = BashConfig(script="terraform apply", cwd=cwd)
    assert config.print_prefix == "tf_module terraform apply"
