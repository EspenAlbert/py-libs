from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import total_ordering, wraps
from sys import stderr
from threading import RLock
from typing import Any, Callable, Optional, Protocol, TypeVar, Union

from rich.console import Console, Group, JustifyMethod, OverflowMethod, RenderableType
from rich.live import Live
from rich.style import Style
from zero_3rdparty.error import error_and_traceback
from zero_3rdparty.id_creator import simple_id

_live: Live | None = None
_lock = RLock()
_renderables: list[LivePart] = []
_live_is_frozen_attr_name = "__live_is_frozen__"
logger = logging.getLogger(__name__)


def _live_is_frozen() -> bool:
    return getattr(get_live(), _live_is_frozen_attr_name, False)


def _console_hook(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            yield from func(*args, **kwargs)
        except BaseException as e:
            # Ensure that the live console is reset if an error occurs
            # We cannot do any logging here as it will cause a deadlock if the RichHandler is being used
            error_with_tb = error_and_traceback(e)
            stderr.write(f"Error in live console: {error_with_tb}\n")
            reset_live()
            raise e

    return wrapper


def get_live() -> Live:
    global _live
    if _live is not None:
        return _live
    with _lock:
        if _live is None:
            _live = Live(transient=True)
            live_render = _live._live_render
            old_console = live_render.__rich_console__
            live_render.__rich_console__ = _console_hook(old_console)
    return _live


def reset_live() -> None:
    global _live, _renderables
    with _lock:
        if _live is None:
            return
        if _live.is_started:
            _live.stop()
        _renderables = []


class live_frozen:
    def __enter__(self) -> None:
        """Freeze the live updates, preventing any changes to the live renderables."""
        assert not _live_is_frozen(), "Live is already frozen"
        with _lock:
            live = get_live()
            if live.is_started:
                live.stop()
            setattr(live, _live_is_frozen_attr_name, True)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        with _lock:
            live = get_live()
            setattr(live, _live_is_frozen_attr_name, False)
            render_live()  # ensure live starts again


def stop_live() -> bool:
    """Returns was_running"""
    global _live
    with _lock:
        if _live is None or not _live.is_started:
            return False
        _live.stop()
        return True


T = TypeVar("T", bound=Callable)


def pause_live(func: T) -> T:
    """Decorator to ensure that the stdout is "free" from progress updates during the function execution.
    This is useful for input functions in th interactive module and shell processes that require user input."""

    @wraps(func)  # type: ignore
    def wrapper(*args, **kwargs):
        with live_frozen():
            return func(*args, **kwargs)  # type: ignore

    return wrapper  # type: ignore


@total_ordering
@dataclass
class LivePart:
    name: str
    renderable: RenderableType
    order: int = 0

    def __lt__(self, other) -> bool:
        if not isinstance(other, LivePart):
            raise TypeError
        return (self.order, self.name) < (other.order, other.name)


def render_live() -> None:
    if _live_is_frozen():
        return
    global _renderables
    live = get_live()
    with _lock:
        if not _renderables:
            if live.is_started:
                live.stop()
            return
        if not live.is_started:
            live.console.print("")  # avoid last line being overwritten
            live.start()
        _renderables.sort()  # Ensure the renderables are sorted by order and name
        group = Group(*[part.renderable for part in _renderables])
        live.update(group, refresh=True)


class RemoveLivePart(Protocol):
    def __call__(self, *, print_after_removing: bool = False) -> Any: ...


def add_renderable(
    renderable: RenderableType, *, order: int = 0, name: str = ""
) -> RemoveLivePart:
    name = name or simple_id()
    part = LivePart(name=name, renderable=renderable, order=order)
    with _lock:
        _renderables.append(part)
        render_live()

    def remove_renderable(*, print_after_removing: bool = False) -> None:
        global _renderables
        with _lock:
            if print_after_removing:
                get_live().console.print(part.renderable)
            _renderables = [part for part in _renderables if part.name != name]
            render_live()

    return remove_renderable


def get_live_console() -> Console:
    return get_live().console


def print_to_live(
    *objects: Any,
    sep: str = " ",
    end: str = "\n",
    style: Optional[Union[str, Style]] = None,
    justify: Optional[JustifyMethod] = None,
    overflow: Optional[OverflowMethod] = None,
    no_wrap: Optional[bool] = None,
    emoji: Optional[bool] = None,
    markup: Optional[bool] = None,
    highlight: Optional[bool] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    crop: bool = True,
    soft_wrap: Optional[bool] = None,
    new_line_start: bool = False,
):
    get_live_console().print(
        *objects,
        sep=sep,
        end=end,
        style=style,
        justify=justify,
        overflow=overflow,
        no_wrap=no_wrap,
        emoji=emoji,
        markup=markup,
        highlight=highlight,
        width=width,
        height=height,
        crop=crop,
        soft_wrap=soft_wrap,
        new_line_start=new_line_start,
    )


def log_to_live(
    *objects: Any,
    sep: str = " ",
    end: str = "\n",
    style: Optional[Union[str, Style]] = None,
    justify: Optional[JustifyMethod] = None,
    emoji: Optional[bool] = None,
    markup: Optional[bool] = None,
    highlight: Optional[bool] = None,
    log_locals: bool = False,
    _stack_offset: int = 1,
) -> None:
    get_live_console().log(
        *objects,
        sep=sep,
        end=end,
        style=style,
        justify=justify,
        emoji=emoji,
        markup=markup,
        highlight=highlight,
        log_locals=log_locals,
        _stack_offset=_stack_offset + 1,  # +1 to skip this function in the stack trace
    )
