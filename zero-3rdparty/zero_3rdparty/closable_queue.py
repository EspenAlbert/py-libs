from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from contextlib import suppress
from functools import partial
from queue import Empty, Queue
from threading import RLock
from typing import Generator, Generic, TypeVar

logger = logging.getLogger(__name__)

QueueT = TypeVar("QueueT")

_empty = object()


class QueueIsClosed(Exception):
    pass


def _raise_queue_is_closed(item: object, *, queue: ClosableQueue, **kwargs):
    if item is not ClosableQueue.SENTINEL:
        raise QueueIsClosed
    Queue.put(queue, item, **kwargs)


class ClosableQueue(Queue[QueueT], Generic[QueueT]):
    SENTINEL = object()
    __QUEUES: list[ClosableQueue] = []

    def __init__(self, maxsize: int = 0):  # 0 == infinite
        super().__init__(maxsize=maxsize)
        self.__QUEUES.append(self)
        # ensure close doesn't block and can set raise error
        self.mutex = RLock()  # type: ignore

        self.not_empty = threading.Condition(self.mutex)
        self.not_full = threading.Condition(self.mutex)
        self.all_tasks_done = threading.Condition(self.mutex)

    def close(self):
        with self.mutex:
            self.put(self.SENTINEL)  # type: ignore
            self.put = partial(_raise_queue_is_closed, queue=self)  # type: ignore
        with suppress(Exception):
            self.__QUEUES.remove(self)

    def close_safely(self):
        with suppress(QueueIsClosed):
            self.close()

    def __iter__(self) -> Generator[QueueT, None, None]:
        try:
            while True:
                item = super().get(block=True)
                if item is self.SENTINEL:
                    with self.mutex:
                        # ensure next iterator will finish immediately
                        self.queue.append(item)
                        self.not_empty.notify()
                    return  # Cause the thread to exit
                yield item
        except BaseException as e:
            logger.exception(e)
        finally:
            with suppress(ValueError):
                self.task_done()

    def pop(self, default=_empty):
        try:
            out = self.get_nowait()
        except Empty:
            return default
        else:
            if out is self.SENTINEL:
                self.put(self.SENTINEL)  # type: ignore # ensure next iterator will finish immediately
            return out

    def iter_non_blocking(self) -> Iterable[QueueT]:
        next_or_sentinel = partial(self.pop, self.SENTINEL)
        return iter(next_or_sentinel, self.SENTINEL)  # type: ignore

    @classmethod
    def close_all(cls):
        if cls.__QUEUES:
            logger.info("closing all queues")
            for q in list(cls.__QUEUES):  # avoid modification during iteration
                q.close()

    def get(self, block: bool = True, timeout: float | None = None) -> QueueT:
        item = super().get(block, timeout)
        if item is self.SENTINEL:
            self.queue.append(self.SENTINEL)
            raise QueueIsClosed
        return item
