# File generation domain

from .example_gen import generate_group_examples_file, get_example_stability
from .groups import write_groups
from .init_file import write_init
from .pyproject import update_pyproject_toml
from .test_gen import generate_group_test_file

__all__ = [
    "generate_group_examples_file",
    "generate_group_test_file",
    "get_example_stability",
    "update_pyproject_toml",
    "write_groups",
    "write_init",
]
