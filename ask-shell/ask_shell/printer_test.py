from ask_shell.colors import EXTRA_COLORS
from ask_shell.printer import get_color


def test_colors_needs_to_be_re_used_at_some_point():
    colors = [get_color(f"prefix_{i}") for i in range(len(EXTRA_COLORS) * 2)]
    assert len(set(colors)) < len(colors)
