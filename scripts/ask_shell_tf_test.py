from pathlib import Path

from ask_shell.run import run_and_wait
from zero_3rdparty import id_creator
from zero_3rdparty.file_utils import ensure_parents_write_text

_example_script = """\
terraform {
  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "2.4.1"
    }
  }
}

resource "local_file" "this" {
  content  = "Hello, World!"
  filename = "hello.txt"
}"""
main_tf = Path(__file__).parent / "terraform_example/main.tf"

multiline_echo = """\
echo "This is a multiline
command
" & sleep 1 && echo "Done"  """


def run_tf_apply():
    ensure_parents_write_text(
        main_tf, _example_script.replace("World!", id_creator.simple_id())
    )
    run_and_wait(multiline_echo)
    run_and_wait(
        "terraform init",
        cwd=main_tf.parent,
    )
    run_and_wait("terraform apply", cwd=main_tf.parent, user_input=True)


if __name__ == "__main__":
    run_tf_apply()
