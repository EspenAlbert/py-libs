from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering, wraps
from threading import RLock
from typing import Any, Callable, Protocol, TypeVar

from rich.console import Group, RenderableType
from rich.live import Live
from zero_3rdparty.id_creator import simple_id

_live: Live | None = None
_lock = RLock()
_renderables: list[LivePart] = []


def get_live() -> Live:
    global _live
    if _live is not None:
        return _live
    with _lock:
        if _live is None:
            _live = Live(transient=True)
    return _live


def reset_live() -> None:
    global _live, _renderables
    with _lock:
        if _live is None:
            return
        if _live.is_started:
            _live.stop()
        _renderables = []


T = TypeVar("T", bound=Callable)


def pause_live(func: T) -> T:
    """Decorator to ensure that the stdout is "free" from progress updates during the function execution.
    This is useful for input functions in th interactive module and shell processes that require user input."""

    @wraps(func)  # type: ignore
    def wrapper(*args, **kwargs):
        with _lock:
            live = get_live()
            stopped = False
            if live.is_started:
                live.stop()
                stopped = True
            try:
                return func(*args, **kwargs)  # type: ignore
            except BaseException as e:
                raise e
            finally:
                if stopped:
                    live.console.print("")  # avoid last line being overwritten
                    live.start()

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
