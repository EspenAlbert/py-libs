from __future__ import annotations

import logging
from asyncio import CancelledError as _AsyncCancelledError
from asyncio import Future as AsyncFuture
from asyncio import TimeoutError as _AsyncTimeoutError
from asyncio import gather, wrap_future
from collections.abc import Iterable
from concurrent.futures import CancelledError as _CancelledError
from concurrent.futures import Future as _ConcFuture
from concurrent.futures import TimeoutError as _ConcTimeoutError
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, TypeVar, Union

from typing_extensions import TypeAlias

logger = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")
ConcFuture = _ConcFuture
ConcCancelledError = _CancelledError
ConcTimeoutError = _ConcTimeoutError
AsyncTimeoutError = _AsyncTimeoutError
AsyncCancelledError = _AsyncCancelledError

Future: TypeAlias = Union[ConcFuture[ResultT], AsyncFuture[ResultT]]


def gather_conc_futures(futures: Iterable[ConcFuture]) -> AsyncFuture:
    return gather(*[wrap_future(f) for f in futures])


def chain_future(
    complete_first: Future, complete_after: Future, only_on_error: bool = False
) -> None:
    def copy_result(future: Future):
        assert future is complete_first
        if complete_after.done():
            logger.info(f"complete_after future already done: {complete_after}")
            return
        if error := complete_first.exception():
            safe_complete(complete_after, error=error)
        else:
            if not only_on_error:
                safe_complete(complete_after, result=complete_first.result())

    complete_first.add_done_callback(copy_result)


def add_done_callback(
    future: Future,
    call: Callable,
    *,
    _only_on_ok: bool = False,
    _only_on_error: bool = False,
    _include_error: bool = False,
    _include_error_name: str = "error",
    **callback_kwargs,
) -> None:
    assert not (_only_on_error and _only_on_ok), "only_on_xx is mutually exclusive"

    @wraps(call)
    def on_complete(f: Future):
        error = f.exception()
        if _only_on_ok and error:
            return
        elif _only_on_error and not error:
            return
        if _include_error:
            callback_kwargs[_include_error_name] = error
        call(**callback_kwargs)

    future.add_done_callback(on_complete)


def add_done_callback_ignore_errors(
    future: Future,
    call: Callable,
    *errors: type[Exception],
    _only_on_ok: bool = False,
    _only_on_error: bool = False,
    **callback_kwargs,
) -> None:
    assert not (_only_on_error and _only_on_ok), "only_on_xx is mutually exclusive"

    @wraps(call)
    def on_complete(f: Future):
        if _only_on_ok and f.exception():
            return
        elif _only_on_error and not f.exception():
            return
        try:
            call(**callback_kwargs)
        except Exception as e:
            if not isinstance(e, errors):
                raise e

    future.add_done_callback(on_complete)


def safe_complete(
    future: Future,
    error: BaseException | None = None,
    result: object | None = None,
):
    if error:
        # asyncio.CancelledError(BaseException)
        assert isinstance(error, BaseException), f"not an error: {error!r}"
    if future.done():
        logger.warning(
            f"future already complete: {future}, error={error}, result={result}"
        )
        return
    if error:
        future.set_exception(error)
    else:
        future.set_result(result)


def safe_error(future: Future) -> BaseException | None:
    if not future.done():
        return None
    try:
        return future.exception()
    except (
        ConcCancelledError,
        ConcTimeoutError,
        AsyncTimeoutError,
        AsyncCancelledError,
    ) as e:
        return e


def safe_result(future: Future) -> Any:
    if not future.done():
        logger.warning("cannot get result, not done")
        return None
    with suppress(BaseException):
        return future.result()


def as_incomplete_future(future: Future | None, fut_type: type = ConcFuture) -> Future:
    if future and not future.done():
        return future
    return fut_type()


def safe_cancel(future: Future | None, reason: str = "") -> None:
    if future and not future.done():
        future.cancel()
    return None


def safe_wait(future: Future[ResultT], timeout: float | None = None) -> ResultT | None:
    if not future:
        logger.warning("no future to wait for")
    try:
        if isinstance(future, ConcFuture):
            return future.result(timeout)
        return future.result()
    except Exception as e:
        logger.exception(e)
    return None


def on_error_ignore(*error_t: type[BaseException]) -> Callable[[BaseException], None]:
    def on_error(error: BaseException):
        if isinstance(error, error_t):
            logger.info(f"ignored error: {error!r}")
            return
        logger.exception(error)

    return on_error
